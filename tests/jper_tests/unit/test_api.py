"""
Unit tests for the JPER API class
"""
import requests
import os
from flask import current_app
from octopus.lib.paths import get_real_path
from octopus.lib import http
from octopus.modules.store import store
from router.shared.models.account import AccOrg
from router.shared.models.note import UnroutedNotification
from router.jper.web_main import app_decorator
from router.jper.api import JPER, ValidationException, ContentException, ValidationMetaException
from router.jper.pub_testing import init_pub_testing
from tests.jper_tests.fixtures.testcase import JPERTestCase
from tests.jper_tests.fixtures.packages import PackageFactory
from tests.jper_tests.fixtures.api import APIFactory
from tests.fixtures.factory import AccountFactory


class MockResponse:
    def __init__(self, status_code):
        self.status_code = status_code


def mock_get_stream(*args, **kwargs):
    if args[0] in ("http://example.com/article/1", "http://example.com/article/1/pdf"):
        return MockResponse(200), "a bunch of text", 5000


def get_stream_fail(*args, **kwargs):
    return None, "", 0


def get_stream_status(*args, **kwargs):
    return MockResponse(401), "", 6000


def get_stream_empty(*args, **kwargs):
    return MockResponse(200), "", 0


class TestAPI(JPERTestCase):

    @classmethod
    def setUpClass(cls):
        # List the tables (by table name) needed for testing
        cls.tables_for_testing = ['account', 'acc_user', 'notification', 'notification_account']
        super().setUpClass()

    @app_decorator
    def setUp(self):
        # need to do this first, before kicking upstairs, as ESTestCase runs initialise
        super(TestAPI, self).setUp()

        # now call the superclass, which will init the app
        self.old_get_stream = http.get_stream
        self.custom_zip_path = get_real_path(__file__, "..", "resources", "custom.zip")

    @app_decorator
    def tearDown(self):
        super(TestAPI, self).tearDown()
        http.get_stream = self.old_get_stream
        if os.path.exists(self.custom_zip_path):
            os.remove(self.custom_zip_path)

    @app_decorator
    def test_01_validate(self):
        # 3 different kinds of validation required
        acc = AccOrg()
        acc.id = 12345
        pub_test = init_pub_testing(acc)

        # 1. Validation of plain metadata-only notification
        notification = APIFactory.incoming_notification_dict(good_affs=True, no_links=True)
        JPER.validate(acc, notification, pub_test=pub_test)

        # 2. Validation of metadata-only notification with external file links
        pub_test.new_submission()
        http.get_stream = mock_get_stream
        notification = APIFactory.incoming_notification_dict(good_affs=True)
        JPER.validate(acc, notification, pub_test=pub_test)

        # 3. Validation of metadata + zip content
        pub_test.new_submission()
        notification = APIFactory.incoming_notification_dict(with_content=True, good_affs=True, no_links=True)
        filepath = PackageFactory.example_package_path()
        with open(filepath, "rb") as f:
            JPER.validate(acc, notification, f, pub_test=pub_test)

    @app_decorator
    def test_02_validate_metadata_only_fail(self):
        acc = AccOrg()
        acc.id = 12345
        pub_test = init_pub_testing(acc)

        # 1. JSON is invalid structure
        with self.assertRaises(ValidationException) as exc:
            JPER.validate(acc, {"random": "content"}, pub_test=pub_test)
        assert str(exc.exception) == "Validation: 12 errors & 7 issues found in raw notification metadata"

        # 2. No match data present
        pub_test.new_submission()
        with self.assertRaises(ValidationMetaException) as exc:
            JPER.validate(acc, {}, pub_test=pub_test)
        assert str(exc.exception) == "Validation: 13 errors & 7 issues found"
        assert "Found no actionable routing metadata in notification" in pub_test.errors[-1]

    @app_decorator
    def test_03_validate_metadata_links_fail(self):
        acc = AccOrg()
        acc.id = 12345
        pub_test = init_pub_testing(acc)

        # 3. No url provided
        notification = APIFactory.incoming_notification_dict(good_affs=True)
        del notification["links"][0]["url"]
        del notification["links"][1]
        with self.assertRaises(ValidationMetaException) as exc:
            JPER.validate(acc, notification, pub_test=pub_test)
        assert "Validation: 1 error" in str(exc.exception)
        assert "1 of the 1 supplied «links» had no URL" == pub_test.errors[0]

        # 4. HTTP connection failure
        pub_test.new_submission()
        notification = APIFactory.incoming_notification_dict(good_affs=True)
        del notification["links"][1]
        http.get_stream = get_stream_fail
        with self.assertRaises(ValidationMetaException) as exc:
            JPER.validate(acc, notification, pub_test=pub_test)
        assert "Validation: 1 error" in str(exc.exception)
        assert "Unable to connect to server to retrieve «link.url»" in pub_test.errors[0]

        # 5. Incorrect status code
        pub_test.new_submission()
        notification = APIFactory.incoming_notification_dict(good_affs=True)
        del notification["links"][1]
        http.get_stream = get_stream_status
        with self.assertRaises(ValidationMetaException) as exc:
            JPER.validate(acc, notification, pub_test=pub_test)
        assert "Validation: 1 error" in str(exc.exception)
        assert "Couldn't download content from «link.url»" in pub_test.errors[0]

        # 6. Empty content
        pub_test.new_submission()
        notification = APIFactory.incoming_notification_dict(good_affs=True)
        del notification["links"][1]
        http.get_stream = get_stream_empty
        with self.assertRaises(ValidationMetaException) as exc:
            JPER.validate(acc, notification, pub_test=pub_test)
        assert "Validation: 1 error" in str(exc.exception)
        assert "Received no content when downloading from «link.url»" in pub_test.errors[0]

    @app_decorator
    def test_04_validate_metadata_content_fail(self):
        acc = AccOrg()
        acc.id = 12345
        pub_test = init_pub_testing(acc)

        # 7. No format supplied
        notification = APIFactory.incoming_notification_dict(good_affs=True, no_links=True)
        path = PackageFactory.example_package_path()
        with open(path, "rb") as f:
            with self.assertRaises(ValidationException) as exc:
                JPER.validate(acc, notification, f, pub_test=pub_test)
            assert "Validation: 1 error" in str(exc.exception)
            assert "If zipped content is provided, metadata must specify packaging format" == pub_test.errors[0]

        # 8. Incorrect format supplied
        pub_test.new_submission()
        notification = APIFactory.incoming_notification_dict(with_content=True, good_affs=True, no_links=True)
        notification["content"]["packaging_format"] = "http://some.random.url"
        path = PackageFactory.example_package_path()
        with open(path, "rb") as f:
            with self.assertRaises(ValidationException) as exc:
                JPER.validate(acc, notification, f, pub_test=pub_test)
            assert "Validation: 1 error" in str(exc.exception)
            assert "No handler for package format 'http://some.random.url'" in pub_test.errors[0]

        # 9. Package invalid/corrupt
        pub_test.new_submission()
        notification = APIFactory.incoming_notification_dict(with_content=True, good_affs=True, no_links=True)
        PackageFactory.make_custom_zip(self.custom_zip_path, corrupt_zip=True)
        with open(self.custom_zip_path, "rb") as f:
            with self.assertRaises(ValidationException) as exc:
                JPER.validate(acc, notification, f, pub_test=pub_test)
            assert "Validation: 1 error" in str(exc.exception)
            assert "Cannot read zip file - File is not a zip file" in pub_test.errors[0]

        # 10. No match data in either md or package
        pub_test.new_submission()
        notification = APIFactory.incoming_notification_dict(with_content=True, no_match_data=True, no_links=True)
        PackageFactory.make_custom_zip(self.custom_zip_path, jats_no_match_data=True)
        with open(self.custom_zip_path, "rb") as f:
            with self.assertRaises(ValidationException) as exc:
                JPER.validate(acc, notification, f, pub_test=pub_test)
            assert 'Validation: 5 errors & 5 issues found' == str(exc.exception)
            assert self.in_list_comparison(
                ['No article PDF file was found in zip file: custom.zip',
                 ('While enhancing metadata -',  ['In publication_date, the «date» values differ: base (2015-01-01), new (2015-03-19)', 'In article identifier, the «id» values differ: base (10.pp/jit.1), new (10.3389/fchem.2015.00017)']),
                 '«metadata.author» has missing field: «affiliations» among the array elements',
                 "In the «metadata.author» array, 0 of the 7 authors has an ORCID specified (in an «identifier» element); at least one and ideally all authors should have an ORCID specified",
                 'Found no actionable routing metadata in notification or associated package'],
                pub_test.errors
            )
            assert self.in_list_comparison([
                ("«metadata.contributor.affiliations» has missing desirable fields: ", ["«country»", "«org»", "«street»", "«city»", "«postcode»", "«identifier»"]),
                "In «metadata.license_ref» a non-creativecommons licence URL 'http://some-url/ok' appears - may be OK if intentional",
                ("«metadata.funding» has missing desirable fields: ", ["«grant_numbers»", "«identifier»"]),
                ("«metadata.author.type» has irregular values:",
                 ["'an author'", "'assisting author'", "among the array elements - preferred values are: ['author', 'corresp']"]),
                "«metadata.author» has missing desirable field: «identifier» among the array elements"
            ],
                pub_test.issues
            )

        # 11. Content / packaging_format specified, but no file
        pub_test.new_submission()
        notification = APIFactory.incoming_notification_dict(with_content=True, good_affs=True, no_links=True)
        with self.assertRaises(ValidationException) as exc:
            JPER.validate(acc, notification, pub_test=pub_test)
        assert "Validation: 1 error" in str(exc.exception)
        assert "«content.packaging_format» (https://pubrouter.jisc.ac.uk/FilesAndJATS) was specified but no package file was submitted" \
               == pub_test.errors[0]

        # 12. No PDF in package
        pub_test.new_submission()
        PackageFactory.make_custom_zip(self.custom_zip_path, inc_pdf=False)
        notification = APIFactory.incoming_notification_dict(with_content=True, good_affs=True, no_links=True)
        with open(self.custom_zip_path, "rb") as f:
            with self.assertRaises(ValidationException) as exc:
                JPER.validate(acc, notification, f, pub_test=pub_test)
            assert "Validation: 3 errors & 9 issues found" in str(exc.exception)
            assert "No article PDF file was found in zip file: custom.zip" in pub_test.errors

        # 13. JATS error (bad article-version)
        pub_test.new_submission()
        notification = APIFactory.incoming_notification_dict(with_content=True, good_affs=True)
        PackageFactory.make_custom_zip(self.custom_zip_path, jats_errors=True, inc_pdf=True)
        with open(self.custom_zip_path, "rb") as f:
            with self.assertRaises(ValidationException) as exc:
                JPER.validate(acc, notification, f, pub_test=pub_test)
            assert "Validation: 1 error" in str(exc.exception)
            assert "Problem extracting data from zip file" in pub_test.errors[0]
            assert "Problem processing JATS metadata: Invalid JAV article-version-type: 'BAD' in <article-version> element" in pub_test.errors[0]

    @app_decorator
    def test_05_create_notification(self):
        # 3 different create mechanisms: (1) Metadata only; (2) Metadata + Streamed file; (3) Metadata + Local file

        store_handler = store.StoreFactory.get()

        # make some accounts that we'll be doing the test as
        acc1 = AccountFactory.publisher_account()

        ### 1. Creation of plain metadata-only notification (with links that aren't checked)
        notification = APIFactory.incoming_notification_dict()
        note = JPER.create_unrouted_note(acc1, notification)
        assert note is not None
        assert note.id is not None
        check = UnroutedNotification.pull(note.id)
        assert check is not None
        assert len(check.links) == 2
        assert check.links[0]["url"] == "http://example.com/article/1"
        assert check.links[1]["url"] == "http://example.com/article/1/pdf"
        assert check.provider_id == acc1.id

        # Now delete the unrouted notification
        num_notes_deleted, num_pkgs_deleted, num_pkgs_delete_failed = JPER.delete_unrouted_notifications_and_files([note.id], [])
        assert num_notes_deleted == 1
        assert num_pkgs_deleted == 0
        assert num_pkgs_delete_failed == 0
        check = UnroutedNotification.pull(note.id)
        assert check is None

        ### 2. Creation of metadata + zip content (from open file ~ streamed)
        notification = APIFactory.incoming_notification_dict(with_content=True, no_links=True)

        filepath = PackageFactory.example_package_path()
        with open(filepath, "rb") as file_handle:
            # This should create notification and store the zip package
            note = JPER.create_unrouted_note(acc1, notification, file_handle)

        assert note is not None
        assert note.id is not None
        check = UnroutedNotification.pull(note.id)
        assert check is not None
        assert check.provider_id == acc1.id
        stored = store_handler.list(note.id)
        assert len(stored) == 2

        # Now delete the unrouted notification and files
        num_notes_deleted, num_pkgs_deleted, num_pkgs_delete_failed = JPER.delete_unrouted_notifications_and_files([], [note.id])
        assert num_notes_deleted == 1
        assert num_pkgs_deleted == 1
        assert num_pkgs_delete_failed == 0
        check = UnroutedNotification.pull(note.id)
        assert check is None
        stored = store_handler.list(note.id)
        assert stored is None


        ### 3. Create from  metadata + zip content in Local File
        notification = APIFactory.incoming_notification_dict(with_content=True, no_links=True)
        PackageFactory.make_custom_zip(self.custom_zip_path, example_zip=True)
        note = JPER.create_unrouted_note(acc1, notification, file_path=self.custom_zip_path)

        assert note is not None
        assert note.id is not None
        check = UnroutedNotification.pull(note.id)
        assert check is not None
        assert check.provider_id == acc1.id
        stored = store_handler.list(note.id)
        assert len(stored) == 2

        # Now delete the unrouted notification and files
        num_notes_deleted, num_pkgs_deleted, num_pkgs_delete_failed = JPER.delete_unrouted_notifications_and_files([], [note.id])
        assert num_notes_deleted == 1
        assert num_pkgs_deleted == 1
        assert num_pkgs_delete_failed == 0
        check = UnroutedNotification.pull(note.id)
        assert check is None
        stored = store_handler.list(note.id)
        assert stored is None

        # Now delete the unrouted notification and files
        num_notes_deleted, num_pkgs_deleted, num_pkgs_delete_failed = JPER.delete_unrouted_notifications_and_files([], [note.id])
        assert num_notes_deleted == 0
        assert num_pkgs_deleted == 0
        assert num_pkgs_delete_failed == 1

    @app_decorator
    def test_06_extract_email_from_affiliation(self):
        # Test that the cleaning method works as expected. That is, if an email exists within an author's
        # affiliation info, ensure that it is added to the author's identifiers
        # make some  accounts that we'll be doing the test as
        acc1 = AccountFactory.publisher_account()

        notification = APIFactory.incoming_notification_dict()
        # add an email to the affiliation field of one of our authors
        notification["metadata"]["author"][0]["affiliations"] = [{"raw": "Some string with an email anotheremail@example.com in it"}]
        notification["metadata"]["author"][0]["identifier"] = []
        note = JPER.create_unrouted_note(acc1, notification)
        assert note is not None
        assert note.id is not None
        # make sure that one of the author identifiers contains "anotheremail@example.com" (which we put into an
        # author's affiliation info)
        email_found_in_affiliation = False
        for author in note.authors:
            for ident in author.get("identifier", []):
                if ident["type"] == "email" and ident["id"] == "anotheremail@example.com":
                    email_found_in_affiliation = True
        assert email_found_in_affiliation

    @app_decorator
    def test_07_create_fail(self):
        # There are 5 circumstances under which the notification will fail

        # make account that we'll be doing the test as
        acc = AccountFactory.publisher_account()

        # 1. Invalid notification metadata
        with self.assertRaises(ValidationException) as exc:
            JPER.create_unrouted_note(acc, {"random": "content"})
        assert "Problem with notification metadata: Field 'random' is not permitted at 'root'" == str(exc.exception)

        # Notification used by remaining tests in this func
        notification = APIFactory.incoming_notification_dict(with_content=True)

        # 2. Corrupt zip file
        PackageFactory.make_custom_zip(self.custom_zip_path, corrupt_zip=True)

        del notification["links"]

        with self.assertRaises(Exception) as exc:
            JPER.create_unrouted_note(acc, notification, file_path=self.custom_zip_path)
        exception_msg = str(exc.exception)
        assert "Problem reading file" in exception_msg
        assert "Error: Cannot read zip file - File is not a zip file" in exception_msg

        with open(self.custom_zip_path, "rb") as f:
            with self.assertRaises(Exception) as exc:
                JPER.create_unrouted_note(acc, notification, f)
            exception_msg = str(exc.exception)
            assert "Problem reading file" in exception_msg
            assert "Error: Cannot read zip file - File is not a zip file" in exception_msg

            pub_test = init_pub_testing(acc)
            with self.assertRaises(ValidationException) as exc:
                JPER.validate(acc, notification, f, pub_test=pub_test)
            assert "Validation: 1 error" in str(exc.exception)


        # 3. Metadata has content.packaging_format specified, but no file provided
        with self.assertRaises(ContentException) as exc:
            JPER.create_unrouted_note(acc, notification)
        assert '«content.packaging_format» (https://pubrouter.jisc.ac.uk/FilesAndJATS) was specified but no package file was submitted'\
               == str(exc.exception)

        # 4. Metadata enhancement exception
        PackageFactory.make_custom_zip(self.custom_zip_path)    # Make zip file WITHOUT a PDF file
        # Exception raised here is due to mismatch between data provided in notification dict & the zip file
        with self.assertRaises(ValidationException) as exc:
            JPER.create_unrouted_note(acc, notification, file_path=self.custom_zip_path)
        assert str(exc.exception).startswith("Problem with notification metadata: EnhancementException")

        with open(self.custom_zip_path, "rb") as f:
            # Exception raised here is due to mismatch between data provided in notification dict & the zip file
            with self.assertRaises(ValidationException) as exc:
                JPER.create_unrouted_note(acc, notification, f)
            assert str(exc.exception).startswith("Problem with notification metadata: EnhancementException")

    @app_decorator
    def test_08_public_docs(self):
        # Test that something exists at the docs url
        docu_base_url = current_app.config.get("DOCU_BASE_URL")

        assert docu_base_url
        # Need to appear as a browser as github now expects that
        assert requests.get(docu_base_url, headers={'User-agent': 'PubRouter unit test/1.0'}).status_code == 200
