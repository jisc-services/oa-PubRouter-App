"""
Tests the authentication and the entire repository implementation for JPER's SWORD api.
"""
import os
from werkzeug.exceptions import HTTPException
from flask import current_app, request
from flask_login import login_user, logout_user, current_user
from octopus.lib.paths import get_real_path
from octopus.lib.files import AlwaysBytesIO
from router.shared.models.note import UnroutedNotification
# We need to import from `outer.jper.app`, rather than `router.jper_sword_in.app`, because JPERTestCase class use this
from router.jper.app import app, app_decorator
from router.jper_sword_in.models.sword import JPERRepository, JPERSwordAuth, SwordInDepositRecord
from router.jper.views.account import blueprint as account
from sword2.server.exceptions import RepositoryError
from sword2.tests.fixtures import entry

from tests.fixtures.factory import AccountFactory
from tests.jper_tests.fixtures.testcase import JPERTestCase
from tests.jper_tests.fixtures.sword import basic_auth
from tests.jper_tests.fixtures.packages import PackageFactory

try:
    # Blueprint Needed because an email template used by PubTesting uses url_for('account.test_record', ...)
    app.register_blueprint(account, url_prefix="/account")  # Needed for pub_test email
except ValueError:
    # This exception occurs when running all pytests because it doesn't seem to flush imports between successive test files
    # and web_main.py performs the same registration
    pass

class TestSwordRepository(JPERTestCase):

    @classmethod
    def setUpClass(cls):
        # List the tables (by table name) needed for testing
        cls.tables_for_testing = ['account', 'acc_user', 'pub_deposit', 'notification', 'pub_test']
        super().setUpClass()


    def create_collection_and_publisher(self, in_test=False, route_note=False):
        publisher = self.create_publisher_and_login(in_test=in_test, route_note=route_note)
        return self.get_collection(publisher), publisher

    def get_collection(self, publisher):
        return self.repo.get_collection(publisher.uuid)

    def create_publisher_and_login(self, in_test=False, route_note=False):
        publisher = AccountFactory.publisher_account()
        if in_test:
            pub_data = publisher.publisher_data
            pub_data.init_testing()
            pub_data.test_type = "u"
            pub_data.in_test = True
            pub_data.route_note = route_note
            publisher.update()
        if current_user and not current_user.is_anonymous:
            logout_user()
        login_user(publisher)
        return publisher

    def create_admin_and_login(self):
        admin = AccountFactory.admin_account()
        if current_user and not current_user.is_anonymous:
            logout_user()
        login_user(admin)
        return admin

    def create_container(self, collection):
        container = collection.create_container(None)
        # last_updated isn't set if a container is created without an entry or a binary deposit
        # Set this so we can create a feed
        container._set_updated_and_store_metadata()
        return container

    def create_all(self):
        collection, publisher = self.create_collection_and_publisher()
        return collection, publisher, self.create_container(collection)

    def setUp(self):
        super().setUp()

        self.repo = JPERRepository()
        self.custom_zip_path = get_real_path(__file__, "..", "resources", "custom.zip")

    def tearDown(self):
        super().tearDown()
        try:
            if os.path.exists(self.custom_zip_path):
                os.remove(self.custom_zip_path)
        except Exception:
            pass

    @app_decorator
    def test_get_collection(self):
        """
        Get a fake collection, which should be None. Then get the actual collection.
        """
        with current_app.test_request_context():
            publisher = self.create_publisher_and_login()
            assert self.repo.get_collection("I am not a collection") is None
            assert self.repo.get_collection(publisher.uuid) is not None
            # Admin should still be able to access
            self.create_admin_and_login()
            assert self.repo.get_collection(publisher.uuid) is not None

    @app_decorator
    def test_list_collections(self):
        """
        List all the collections in the repository. There should only be one for the logged in publisher.
        """
        with current_app.test_request_context():
            publisher = self.create_publisher_and_login()
            # Make a second publisher and a second collection
            AccountFactory.publisher_account()
            collections = self.repo.collections
            assert len(collections) == 1
            assert collections[0].id == str(publisher.uuid)
            # Login an admin account
            self.create_admin_and_login()
            assert len(self.repo.collections) == 2

    @app_decorator
    def test_create_container(self):
        """
        Create a collection, and create a default container with that collection.
        """
        # Need test_request_context for flask_login
        with current_app.test_request_context():
            publisher = self.create_publisher_and_login()
            collection = self.get_collection(publisher)
            container = collection._create_container_with_id()
        assert container.id == "1"
        assert container.in_progress
        # Check the account id in the database object
        assert container.record.publisher_id == publisher.id

    @app_decorator
    def test_get_container(self):
        """
        Get a container that doesn't exist, which should return None.
        Create a container, and then get it - which should have the same data as the
        created container.
        """
        with current_app.test_request_context():
            collection, publisher, created_container = self.create_all()
            container = collection.get_container("Not a container")
            assert container is None
            container = collection.get_container(created_container.id)
            assert container is not None
            assert container.record.publisher_id == publisher.id

    @app_decorator
    def test_delete_container(self):
        """
        Create a container, get it, delete it, then expect it not to exist.
        """
        with current_app.test_request_context():
            collection, publisher, created_container = self.create_all()
            login_user(publisher)
            container = collection.get_container(created_container.id)
        assert container is not None

        container.delete()
        assert collection.get_container(created_container.id) is None

    @app_decorator
    def test_list_containers(self):
        """
        Create two containers, then make sure the list of containers in the collection
        is the same as what was created.
        """
        with current_app.test_request_context():
            collection, publisher, first_container = self.create_all()
            second_container = self.create_container(collection)

            containers = collection.containers

            assert len(containers) == 2
            assert set(container.id for container in containers) == {first_container.id, second_container.id}

    @app_decorator
    def test_collection_feed(self):
        """
        Create two containers, then make sure the collection's feed lists the containers.
        """
        with current_app.test_request_context():
            collection, publisher, first_container = self.create_all()
            self.create_container(collection)

            feed = collection.to_feed()
            assert len(feed.entries) == 2

    @app_decorator
    def test_binary_deposit(self):
        """
        Create a container by depositing a binary file.

        Test variations including failures - particularly attempting to mix Zip & Non-zip, or multiple-zip
        """
        my_text_file = AlwaysBytesIO("my text")
        PackageFactory.make_custom_zip(self.custom_zip_path, inc_pdf=True)
        zip_file = open(self.custom_zip_path, "rb")

        with current_app.test_request_context():
            collection, publisher = self.create_collection_and_publisher()

            # Deposit a single file into Collection
            container = collection.deposit_binary(my_text_file, "text.txt")
            assert set(container.contents) == {"text.txt"}
            assert container.record.name == "text.txt"
            assert container.has_part[0] == "text.txt"

            # Deposit another file into Container
            container.add_or_replace_binary_file(my_text_file, "another.txt")
            assert set(container.contents) == {"text.txt", "another.txt"}
            assert container.record.name == "text.txt"  # UNCHANGED
            assert container.has_part == ["text.txt", "another.txt"]

            # Attempt Zip deposit another file in Container - should fail as don't allow mixture of zip & non-zip
            with self.assertRaises(RepositoryError) as exc:
                container.add_or_replace_binary_file(zip_file, "zippy.zip")
            assert str(exc.exception) == "('Prohibited file combination', \"Cannot mix Zip and non-Zip files; you attempted to store 'zippy.zip', but non-zip files were previously stored.\")"

            # Empty container - to enable subsequent tests to continue
            container.delete_content(None)
            assert container.contents == []
            assert container.record.name == container.INIT_FILENAME
            assert container.has_part == []

            # Now add a zip file
            container.add_or_replace_binary_file(zip_file, "zippy.zip")
            assert set(container.contents) == {"zippy.zip"}
            assert container.record.name == "zippy.zip"  # UNCHANGED
            assert container.has_part == ["zippy.zip"]

            # Now Replace a zip file
            container.add_or_replace_binary_file(zip_file, "zippy.zip")
            assert set(container.contents) == {"zippy.zip"}
            assert container.record.name == "zippy.zip"  # UNCHANGED
            assert container.has_part == ["zippy.zip"]

            # Attempt 2nd Zip deposit in Container - it should fail as only 1 zip allowed
            with self.assertRaises(RepositoryError) as exc:
                container.add_or_replace_binary_file(zip_file, "zippy_2.zip")
            assert str(exc.exception) == "('Prohibited file combination', \"Only one Zip file allowed; you attempted to store 'zippy_2.zip', but 'zippy.zip' was previously stored.\")"

            # Attempt to store non-zip file in Container containing a zip - expect it to fail
            with self.assertRaises(RepositoryError) as exc:
                container.add_or_replace_binary_file(my_text_file, "some.txt")
            assert str(exc.exception) == "('Prohibited file combination', \"Cannot mix non-Zip and Zip files; you attempted to store 'some.txt', but 'zippy.zip' was previously stored.\")"


    @app_decorator
    def test_metadta_deposit(self):
        """
        Create a container by depositing metadata

        """
        with current_app.test_request_context():
            collection, publisher = self.create_collection_and_publisher()

            # Attempt to Deposit Atom metadata into Collection
            with self.assertRaises(RepositoryError) as exc:
                collection.deposit_metadata(entry)
            assert str(exc.exception) == "('Atom Entry submission prohibited', 'Publications Router ONLY accepts Metadata deposited as a JATS XML file (which may be within a Zip package).')"

            # Create container by adding file
            my_text_file = AlwaysBytesIO("my text")
            container = collection.deposit_binary(my_text_file, "text.txt")
            assert set(container.contents) == {"text.txt"}

            # Attempt to add Atom metadata to container
            with self.assertRaises(RepositoryError) as exc:
                container.update_metadata(entry)
            assert str(exc.exception) == "('Atom Entry submission prohibited', 'Publications Router ONLY accepts Metadata deposited as a JATS XML file (which may be within a Zip package).')"



    @app_decorator
    def test_process_zip_deposit(self):
        """
        Create a container by depositing a zip file.
        assert that the zip file was extracted, process (complete deposit) the container
        and assert that an UnroutedNotification was created.
        """
        PackageFactory.make_custom_zip(self.custom_zip_path, inc_pdf=True)

        zip_file = open(self.custom_zip_path, "rb")

        with current_app.test_request_context():
            collection, publisher = self.create_collection_and_publisher()
            container = collection.deposit_binary(zip_file, "custom.zip")
            zip_file.close()

            assert set(container.contents) == {"custom.zip"}

            container._process_completed_deposit()

            assert UnroutedNotification.count() == 1
            assert SwordInDepositRecord.count(SwordInDepositRecord.__type__, pull_name="all_by_type") == 1
            # Make sure the FTP record is correct
            assert container.record.successful is True
            assert container.record.name == "custom.zip"


    @app_decorator
    def test_autotest_process_zip_deposit(self):
        """
        Create a container by depositing a zip file.
        assert that the zip file was extracted, process (complete deposit) the container
        and assert that an UnroutedNotification was created.
        """
        PackageFactory.make_custom_zip(self.custom_zip_path, inc_pdf=True)

        zip_file = open(self.custom_zip_path, "rb")

        with current_app.test_request_context():
            collection, publisher = self.create_collection_and_publisher(in_test=True)
            container = collection.deposit_binary(zip_file, "custom.zip")
            zip_file.close()

            assert set(container.contents) == {"custom.zip"}

            with self.assertRaises(RepositoryError) as exc:
                container._process_completed_deposit()
            assert 'Failed Deposit Validation: 2 errors and 10 issues found' in str(exc.exception)

            assert UnroutedNotification.count() == 0
            assert SwordInDepositRecord.count(SwordInDepositRecord.__type__, pull_name="all_by_type") == 0

            # Make sure the FTP record is correct
            assert container.record.successful is False



    @app_decorator
    def test_delete_content(self):
        """
        Delete one file from a container, then delete all of the files left in the container.
        """
        PackageFactory.make_custom_zip(self.custom_zip_path)
        zip_file = open(self.custom_zip_path, "rb")

        with current_app.test_request_context():
            collection, publisher = self.create_collection_and_publisher()
            container = collection.deposit_binary(zip_file, "custom.zip")
            assert container.contents == ["custom.zip"]
            assert container.record.name == "custom.zip"
            assert container.has_part[0] == "custom.zip"

            container.delete_content(None)
            assert container.contents == []
            assert container.record.name == container.INIT_FILENAME
            assert container.has_part == []

    @app_decorator
    def test_valid_credentials(self):
        """
        Create an account and login to that account with basic auth.

        Then try login to an account that doesn't exist, and assert that it doesn't exist.
        """
        account = AccountFactory.publisher_account()
        api_key = "TEST-API-KEY"
        account.api_key = api_key
        account.update()
        with current_app.test_request_context():
            JPERSwordAuth.valid_credentials(
                basic_auth(account.uuid, api_key)
            )
            assert current_user is not None
            assert current_user.id == account.id
            logout_user()
            JPERSwordAuth.valid_credentials(
                basic_auth("bademail@email.email", "notapassword")
            )
            assert current_user is None or current_user.is_anonymous

    @app_decorator
    def test_valid_authentication(self):
        """
        Create a container with a publisher, login to that publisher and succeed in authenticating.
        """
        with current_app.test_request_context():
            collection, publisher = self.create_collection_and_publisher()
            container = self.create_container(collection)
            logout_user()

            api_key = "TEST-API-KEY"
            publisher.api_key = api_key
            publisher.update()

            request.authorization = basic_auth(publisher.uuid, api_key)

            JPERSwordAuth.authenticate(collection.id, container.id)

    @app_decorator
    def test_invalid_authentication_not_a_publisher(self):
        """
        Create a container with a publisher, login to a repository and fail authentication.
        """
        with current_app.test_request_context():
            collection, publisher = self.create_collection_and_publisher()
            container = self.create_container(collection)
            logout_user()

            api_key = "TEST-API-KEY"
            repo = AccountFactory.repo_account(live=False)
            repo.api_key = api_key
            repo.update()

            request.authorization = basic_auth(repo.uuid, api_key)

            with self.assertRaises(HTTPException) as exc:
                JPERSwordAuth.authenticate(collection.id, container.id)
            assert exc.exception.response.status_code == 401    # Unauthorized

    @app_decorator
    def test_invalid_authentication_wrong_publisher(self):
        """
        Create a container with a publisher, login to a different publisher, and fail authentication.
        """

        with current_app.test_request_context():
            collection, publisher = self.create_collection_and_publisher()
            container = self.create_container(collection)
            logout_user()

            api_key = "TEST-API-KEY"
            other_pub = AccountFactory.publisher_account()
            other_pub.api_key = api_key
            other_pub.update()

            request.authorization = basic_auth(other_pub.uuid, api_key)

            with self.assertRaises(HTTPException) as exc:
                JPERSwordAuth.authenticate(collection.id, container.id)
            assert exc.exception.response.status_code == 401    # Unauthorized

    @app_decorator
    def test_valid_authentication_admin_account(self):

        with current_app.test_request_context():
            collection, publisher = self.create_collection_and_publisher()
            container = self.create_container(collection)
            logout_user()

            api_key = "admin_password"
            admin = AccountFactory.admin_account()
            admin.api_key = api_key
            admin.update()

            request.authorization = basic_auth(admin.uuid, api_key)

            JPERSwordAuth.authenticate(collection.id, container.id)
