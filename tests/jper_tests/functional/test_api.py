"""
Functional tests for the API.

This will run using the flask test client to avoid requiring an actual running App1 server.
"""
import json
import os
from requests_toolbelt import MultipartEncoder
from sword2.server.multipart import inject_into_werkzeug

from requests_mock import Mocker
from functools import partial
from flask import url_for, current_app, g
from octopus.lib.files import AlwaysBytesIO
from octopus.lib.paths import rel2abs
from tests.jper_tests.fixtures.testcase import JPERTestCase
from tests.jper_tests.fixtures.models import IdentifierFactory
from tests.jper_tests.fixtures.repository import RepositoryFactory
from tests.jper_tests.fixtures.packages import PackageFactory
from tests.jper_tests.fixtures.api import APIFactory
from tests.fixtures.factory import AccountFactory, NotificationFactory
from router.shared.models.note import UnroutedNotification, RoutedNotification
from router.jper.web_main import app_decorator
from router.jper.models.publisher import APIDepositRecord

ADMIN_API_KEY = "admin"
INVALID_API_KEY = "bad-apikey"

inject_into_werkzeug()

class RouterMultipartEncoder(MultipartEncoder):

    @property
    def content_type(self):
        """
        This is the same as the default MultipartEncoder from requests toolbelt - the only difference is that
        it will use multipart/related instead of multipart/form-data.
        """
        return f'multipart/related; boundary={self.boundary_value}'


def flask_response_to_json(response):
    try:
        json_data = json.loads(response.data.decode("utf-8"))
    except UnicodeDecodeError:
        json_data = None
    return json_data


class TestAPI(JPERTestCase):

    @classmethod
    @app_decorator
    def setUpClass(cls):
        """
        Set up flask settings to make sure we use temporary file locations.
        """
        def clear_logged_in_user_after_request(response):
            # logout_user() - Could call this, but not needed

            # Hack LoginManager so it is forced to always fetch user (via apikey), otherwise even after
            # logging out, LoginManager leaves behind the default Anonymous user account, which is then used for
            # subsequent API calls
            g.pop('_login_user', None)
            return response

        # List the tables (by table name) needed for testing
        cls.tables_for_testing = [
            'account', 'acc_user', 'acc_notes_emails', 'pub_deposit', 'notification', 'notification_account', 'pub_test', 'org_identifiers',
            'acc_repo_match_params', 'acc_repo_match_params_archived', 'match_provenance', 'content_log'
        ]
        super().setUpClass()
        # After each API request, we remove trace of logged-in user - so that for each request
        current_app.after_request(clear_logged_in_user_after_request)

    def setUp(self):
        super().setUp()
        self.custom_zip_path = rel2abs(__file__, "..", "resources", "custom.zip")

    def tearDown(self):
        if os.path.exists(self.custom_zip_path):
            os.remove(self.custom_zip_path)
        super().tearDown()

    @staticmethod
    def deposit_record_stats():
        # returns a tuple total_cnt, success_cnt, fail_cnt depending on how many deposit_records there are,
        # how many are successful and how many weren't
        success_count = 0
        total_count = 0
        for deposit_record in APIDepositRecord.get_all():
            total_count += 1
            if deposit_record.successful:
                success_count += 1
        return total_count, success_count, total_count - success_count

    def create_pub_acc(self, live=True, no_default_licence=False, auto_test=False, auto_test_route=False):
        publisher = AccountFactory.publisher_account(live)
        pub_data = publisher.publisher_data
        pub_data.init_testing()
        # For our test purposes, if auto_test is True, we don't need to worry about setting
        # any of values in the testing_dict
        pub_data.in_test = auto_test
        if auto_test_route:
            pub_data.route_note = True
        if no_default_licence:
            pub_data.license = {}

        # Set the publisher to be active
        pub_data.status = 1
        publisher.update()
        self.publisher_api_key = publisher.api_key
        return publisher

    @staticmethod
    def create_file_dict(
            metadata_str, example_package, metadata_ctype="application/json", content_ctype="application/zip"):
        """
        Create a dictionary for multipart requests to JPER.
        """
        # return {
        #     "metadata": ("metadata.json", AlwaysBytesIO(metadata_str), metadata_ctype),
        #     "content": ("content.zip", open(example_package, "rb"), content_ctype)
        # }
        return {
            "metadata": (AlwaysBytesIO(metadata_str), "metadata.json", metadata_ctype),
            "content": (open(example_package, "rb"), "content.zip", content_ctype)
        }

    @staticmethod
    def create_multipart_dict(metadata_str, example_package):
        """
        Create a dictionary for multipart/related requests, for use with the SwordEncoder.
        """
        return {
            "metadata": ("metadata.json", AlwaysBytesIO(metadata_str), "application/json"),
            "content": ("content.zip", open(example_package, "rb"), "application/zip")
        }

    def partial_post(self, view_path, api_key=None):
        # Make a partial of post with the api_key added to url_for - less writing this way.
        if not api_key:
            api_key = ADMIN_API_KEY
        return partial(self.test_client.post, url_for(view_path, api_key=api_key))

    def partial_json_post(self, view_path, api_key=None):
        return partial(self.partial_post(view_path, api_key), content_type="application/json")

    @app_decorator
    @Mocker()
    def test_validation_singlepart(self, mock):
        mock_url = "http://localhost/test/download/file.pdf"
        mock.get(mock_url, text='Some PDF content')
        notification = APIFactory.incoming_notification_dict(good_affs=True)
        for l in notification["links"]:
            l["url"] = mock_url
        self.create_pub_acc()
        resp = self.partial_json_post("v4_api.validate", self.publisher_api_key)(data=json.dumps(notification))
        assert resp.status_code == 200

    @app_decorator
    @Mocker()
    def test_validation_singlepart_fail(self, mock):
        # ways in which the validation http request can fail
        # 1. invalid/wrong auth credentials
        # FIXME: we can't do this test yet

        # 2. incorrect content-type header
        mock_url = "http://localhost/test/download/file.pdf"
        mock.get(mock_url, text='Some PDF content')
        notification = APIFactory.incoming_notification_dict()
        notification["links"][0]["url"] = mock_url

        self.create_pub_acc()
        partial_post = self.partial_post("v4_api.validate", self.publisher_api_key)

        resp = partial_post(data=json.dumps(notification), content_type="text/plain")
        assert resp.status_code == 400
        j = resp.json
        assert "errors" in j
        assert "application/json" in j["errors"][0]

        # 3. invalid json
        resp = partial_post(data="garbage", content_type="application/json")
        assert resp.status_code == 400
        j = resp.json
        assert "errors" in j
        assert "Invalid JSON" in j["errors"][0]

    @app_decorator
    @Mocker()
    def test_pub_test_bad_metadata_validation_singlepart_fail(self, mock):
        mock_url = "http://localhost/test/download/file.pdf"
        mock.get(mock_url, text='Some PDF content')
        notification = APIFactory.incoming_notification_dict(bad=True)
        notification["links"][0]["url"] = mock_url
        self.create_pub_acc(no_default_licence=True)
        resp = self.partial_json_post("v4_api.validate", self.publisher_api_key)(data=json.dumps(notification))
        assert resp.status_code == 400
        j = resp.json
        assert j["status"] == "error"
        assert len(j["errors"]) == 25
        assert len(j["issues"]) == 8
        expected_errors = [
            "«metadata.contributor» has empty field: «type» among the array elements",
            "«metadata.contributor.name» has empty field: «surname» among the array elements",
            "«metadata.license_ref» has missing field: «url» among the array elements",
            "In «metadata.license_ref.start» an invalid date '01-01-2015' was found (required format is: YYYY-MM-DD)",
            "A licence «start» date is required for all but one of the «metadata.license_ref» elements (1 were found in 3 licences)",
            "«metadata.funding» has missing field: «name» among the array elements",
            "«metadata.journal.title» is missing",
            "«metadata.journal.identifier» has missing field: «id»",
            "«metadata.article.title» is empty",
            "«metadata.article.version» is empty",
            "«metadata.article.identifier» has empty field: «id» among the array elements",
            "The «metadata.article.identifier» array had 2 DOIs, but only 1 is allowed",
            "«metadata.author» has missing field: «affiliations»; & empty field: «affiliations» among the array elements",
            ('«metadata.author.affiliations» has missing fields:', ['«org»', '«country»', '«city»']),
            "«metadata.author.type» has invalid value: 'BAD' among the array elements - allowed values are: ['author', 'corresp']",
            "«metadata.author.name» has missing field: «firstname»; & empty field: «surname»; & unexpected field: «oops-name» among the array elements",
            ('«metadata.author.identifier» has missing fields: ', ['«type»', '«id»', '; & empty field: «id»; & unexpected field: «oops-id» among the array elements']),
            "In «metadata.accepted_date» an invalid date '01-09-2014' was found (required format is: YYYY-MM-DD)",
            "«event» has invalid value: 'bad_event' - allowed values are: ['submitted', 'accepted', 'published', 'corrected', 'revised']",
            "«metadata.journal.volume» is missing",
            "In «metadata.publication_date» the «Year» field value '2014' did not match the «date» field part '2015' (required format is YYYY)",
            "«metadata.publication_date.publication_format» has invalid value: 'BAD' - allowed values are: ['electronic', 'printed', 'print']",
            "In «metadata.publication_date» the «Month» field value '' did not match the «date» field part '01' (required format is MM)",
            "«metadata.publication_date» has empty field: «month»",
            "Could not create Router record from supplied notification metadata: Field 'oops-name' is not permitted at 'metadata.author[0].name.'"
        ]
        assert self.in_list_comparison(expected_errors, j["errors"]) is True

        expected_issues = [
            "«metadata.contributor» has missing desirable field: «identifier»",
            ('«metadata.contributor.affiliations» has missing desirable fields', ["org", "identifier"]),
            "«metadata.article.subject» is empty",
            "In «metadata.license_ref» a non-creativecommons licence URL 'url' appears",
            '«metadata.ack» is missing (desirable field)',
            "In the «metadata.author» array, 2 of the 3 authors have an ORCID specified",
            ('«metadata.author.affiliations» has missing desirable fields', ["street", "postcode", "identifier", "dept", "country_code"]),
            '«metadata.article.start_page» is missing (desirable field)'
        ]
        assert self.in_list_comparison(expected_issues, j["issues"]) is True

    @app_decorator
    def test_validation_multipart(self):
        notification = APIFactory.incoming_notification_dict(with_content=True, good_affs=True, no_links=True)
        example_package = PackageFactory.example_package_path()
        self.create_pub_acc(auto_test=True, auto_test_route=True)
        # Create repo account to which valid notification will be routed
        AccountFactory.repo_account(live=False, org_name="Jisc-auto-TEST")
        partial_post = self.partial_post("v4_api.validate", self.publisher_api_key)
        encoded_data = RouterMultipartEncoder(self.create_multipart_dict(json.dumps(notification), example_package))
        resp = partial_post(
            data=encoded_data,
            headers={"Content-Type": encoded_data.content_type}
        )
        assert resp.status_code == 200

    @app_decorator
    def test_validation_multipart_fail(self):
        # ways in which the validation http request can fail
        # 1. invalid/wrong auth credentials
        # FIXME: we can't do this test yet

        # 2. Incorrect content-type header on metadata/content parts
        notification = APIFactory.incoming_notification_dict(with_content=True, good_affs=True, no_links=True)
        notification_json = json.dumps(notification)
        example_package = PackageFactory.example_package_path()

        self.create_pub_acc(auto_test=True)

        partial_post = self.partial_post("v4_api.validate", self.publisher_api_key)
        resp = partial_post(data=self.create_file_dict(notification_json, example_package, metadata_ctype="text/plain"))
        assert resp.status_code == 400
        j = resp.json
        assert "errors" in j
        assert "application/json" in j["errors"][0]

        resp = partial_post(data=self.create_file_dict(notification_json, example_package, content_ctype="text/plain"))
        assert resp.status_code == 400
        j = resp.json
        assert "errors" in j
        assert "application/zip" in j["errors"][0]

        # 3. Invalid json
        resp = partial_post(data=self.create_file_dict("Not JSON", example_package))
        assert resp.status_code == 400
        j = resp.json
        assert "errors" in j
        assert "Invalid JSON" in j["errors"][0]

        # 4. Incorrect content type
        resp = partial_post(data=self.create_file_dict(notification_json, example_package), content_type="multipart/form-data")
        assert resp.status_code == 200
        j = resp.json
        assert "issues" in j
        assert "multipart/related" in j["issues"][0]

        # 5. Too many files
        data = self.create_multipart_dict(notification_json, example_package)
        data["extra"] = ("plain.txt", AlwaysBytesIO("Text file"), "text/plain")
        encoded_data = RouterMultipartEncoder(data)
        resp = partial_post(
            data=encoded_data,
            headers={"Content-Type": encoded_data.content_type}
        )
        assert resp.status_code == 200
        j = resp.json
        assert "issues" in j
        assert "2 required files" in j["issues"][0]

        # 6. Bad zip file - not a real zip
        PackageFactory.make_custom_zip(self.custom_zip_path, corrupt_zip=True)
        resp = partial_post(data=self.create_file_dict(notification_json, self.custom_zip_path))
        assert resp.status_code == 400
        j = resp.json
        assert "errors" in j
        assert "Cannot read zip file" in j["errors"][0]

        # 7. Bad zip file - Invalid XML in zip
        PackageFactory.make_custom_zip(self.custom_zip_path, invalid_jats=True)
        resp = partial_post(data=self.create_file_dict(notification_json, self.custom_zip_path))
        assert resp.status_code == 400
        j = resp.json
        assert "errors" in j
        assert "No JATS metadata found in package" in j["errors"][0]

        # 8. Bad zip file - No XML file
        PackageFactory.make_custom_zip(self.custom_zip_path, no_jats=True, inc_pdf=True)
        resp = partial_post(data=self.create_file_dict(notification_json, self.custom_zip_path))
        assert resp.status_code == 400
        j = resp.json
        assert "errors" in j
        assert "No JATS metadata found in package" in j["errors"][0]

        # 9. Bad zip file - Empty zip
        PackageFactory.make_custom_zip(self.custom_zip_path, no_jats=True)
        resp = partial_post(data=self.create_file_dict(notification_json, self.custom_zip_path))
        assert resp.status_code == 400
        j = resp.json
        assert "errors" in j
        assert "No JATS metadata found in package" in j["errors"][0]

        # 10. Bad Packaging format
        notification["content"]["packaging_format"] = "BAD-PKG-FORMAT"
        notification_json = json.dumps(notification)

        resp = partial_post(data=self.create_file_dict(notification_json, example_package))
        assert resp.status_code == 400
        j = resp.json
        assert "errors" in j
        assert "No handler for package format 'BAD-PKG-FORMAT'" in j["errors"][0]

        # 11. No Packaging format
        del notification["content"]["packaging_format"]
        notification_json = json.dumps(notification)

        resp = partial_post(data=self.create_file_dict(notification_json, example_package))
        assert resp.status_code == 400
        j = resp.json
        assert "errors" in j
        assert "metadata must specify packaging format" in j["errors"][0]

    @app_decorator
    def test_create_notification_singlepart(self):
        notification = APIFactory.incoming_notification_dict()
        # make request as a publisher
        self.create_pub_acc()
        resp = self.partial_json_post("v4_api.create_notification", self.publisher_api_key)(data=json.dumps(notification))
        assert resp.status_code == 201
        j = resp.json
        assert "id" in j
        assert "location" in j
        assert self.deposit_record_stats() == (1, 1, 0)

        # make request as admin
        resp = self.partial_json_post("v4_api.create_notification")(data=json.dumps(notification))
        assert resp.status_code == 201
        # check that a deposit record wasn't created (stats are same)
        assert self.deposit_record_stats() == (1, 1, 0)

    @app_decorator
    def test_create_notification_singlepart_unauthenticated(self):
        # invalid/wrong auth credentials
        resp = self.test_client.post(
            url_for("v4_api.create_notification", api_key=INVALID_API_KEY),
            content_type="application/json"
        )
        assert resp.status_code == 401
        # check no deposit records were created
        assert self.deposit_record_stats() == (0, 0, 0)

    @app_decorator
    def test_create_notification_singlepart_bad_content_type(self):
        # incorrect content-type header
        notification = APIFactory.incoming_notification_dict()
        # make request as publisher
        self.create_pub_acc()
        partial_post = self.partial_post("v4_api.create_notification", self.publisher_api_key)
        resp = partial_post(data=json.dumps(notification), content_type="text/plain")
        assert resp.status_code == 400
        j = resp.json
        assert "error" in j
        assert "application/json" in j["error"]
        # check a failed deposit record was created
        assert self.deposit_record_stats() == (1, 0, 1)
        # make request as admin
        partial_post = self.partial_post("v4_api.create_notification")
        resp = partial_post(data=json.dumps(notification), content_type="text/plain")
        assert resp.status_code == 400
        # check a failed deposit record was NOT created
        assert self.deposit_record_stats() == (1, 0, 1)

    @app_decorator
    def test_create_notification_singlepart_invalid_json(self):
        # invalid json
        # make request as publisher
        self.create_pub_acc()
        resp = self.partial_json_post("v4_api.create_notification", self.publisher_api_key)(data="Garbage")
        assert resp.status_code == 400
        j = resp.json
        assert "error" in j
        assert "Invalid JSON" in j["error"]
        # check failed deposit record was created
        assert self.deposit_record_stats() == (1, 0, 1)
        # make request as admin
        resp = self.partial_json_post("v4_api.create_notification")(data="Garbage")
        assert resp.status_code == 400
        # check failed deposit record was NOT created
        assert self.deposit_record_stats() == (1, 0, 1)

    @app_decorator
    def test_create_notification_singlepart_unstructured_json(self):
        # incorrectly structured json
        obj = {"random": "content"}
        # make request as publisher
        self.create_pub_acc()
        resp = self.partial_json_post("v4_api.create_notification", self.publisher_api_key)(data=json.dumps(obj))
        assert resp.status_code == 400
        j = resp.json
        assert "error" in j
        assert "Field 'random' is not permitted at 'root'" in j["error"]
        # make request as admin
        resp = self.partial_json_post("v4_api.create_notification")(data=json.dumps(obj))
        assert resp.status_code == 400
        # check failed deposit record was NOT created
        assert self.deposit_record_stats() == (1, 0, 1)

    @app_decorator
    def test_create_notification_multipart(self):
        """
        Test creating notification WITH content (i.e. zip deposit) using a Publisher Account & an Admin Account
        """
        notification = APIFactory.incoming_notification_dict(with_content=True)
        example_package = PackageFactory.example_package_path()
        # make request as publisher
        self.create_pub_acc()
        partial_post = self.partial_post("v4_api.create_notification", self.publisher_api_key)
        resp = partial_post(data=self.create_file_dict(json.dumps(notification), example_package))
        assert resp.status_code == 201
        j = resp.json
        assert "id" in j
        assert "location" in j
        assert self.deposit_record_stats() == (1, 1, 0)

        # make request as admin
        partial_post = self.partial_post("v4_api.create_notification")
        resp = partial_post(data=self.create_file_dict(json.dumps(notification), example_package))
        assert resp.status_code == 201
        # make sure deposit record count hasn't changed
        assert self.deposit_record_stats() == (1, 1, 0)

    @app_decorator
    def test_create_notification_multipart_fail_no_pdf(self):
        """
        Test creating notification WITH content (i.e. zip deposit) that is missing PDF
        """
        notification = APIFactory.incoming_notification_dict(with_content=True, no_links=True)
        del notification["metadata"]
        PackageFactory.make_custom_zip(self.custom_zip_path)
        # make request as publisher
        self.create_pub_acc()
        partial_post = self.partial_post("v4_api.create_notification", self.publisher_api_key)
        resp = partial_post(data=self.create_file_dict(json.dumps(notification), self.custom_zip_path))
        assert resp.status_code == 201

        # make request as admin
        partial_post = self.partial_post("v4_api.create_notification")
        resp = partial_post(data=self.create_file_dict(json.dumps(notification), self.custom_zip_path))
        assert resp.status_code == 201

    @app_decorator
    def test_create_notification_multipart_fail_incorrect_content_type_header(self):
        # incorrect content-type header on metadata/content parts
        notification = APIFactory.incoming_notification_dict(with_content=True)
        example_package = PackageFactory.example_package_path()

        partial_post = self.partial_post("v4_api.create_notification")
        resp = partial_post(data=self.create_file_dict(
            json.dumps(notification),
            example_package,
            metadata_ctype="text/plain"
        ))
        assert resp.status_code == 400
        j = resp.json
        assert "error" in j
        assert "application/json" in j["error"]

        resp = partial_post(data=self.create_file_dict(
            json.dumps(notification),
            example_package,
            content_ctype="text/plain"
        ))
        assert resp.status_code == 400
        j = resp.json
        assert "error" in j
        assert "application/zip" in j["error"]

    @app_decorator
    def test_create_notification_multipart_fail_invalid_json(self):
        # invalid json
        example_package = PackageFactory.example_package_path()
        # make request as publisher
        self.create_pub_acc()
        partial_post = self.partial_post("v4_api.create_notification", self.publisher_api_key)
        resp = partial_post(data=self.create_file_dict(
            "Garbage",
            example_package,
        ))
        assert resp.status_code == 400
        j = resp.json
        assert "error" in j
        assert "Invalid JSON" in j["error"]
        assert self.deposit_record_stats() == (1, 0, 1)

    @app_decorator
    def test_create_notification_multipart_validation_exception(self):
        # validation exception on the content
        self.create_pub_acc()
        partial_post = self.partial_post("v4_api.create_notification", self.publisher_api_key)
        notification = APIFactory.incoming_notification_dict(with_content=True)
        PackageFactory.make_custom_zip(self.custom_zip_path, corrupt_zip=True)
        resp = partial_post(data=self.create_file_dict(
            json.dumps(notification),
            self.custom_zip_path
        ))
        assert resp.status_code == 400
        j = resp.json
        assert "error" in j
        assert "Cannot read zip file" in j["error"]
        assert self.deposit_record_stats() == (1, 0, 1)

    @app_decorator
    def test_create_notification_denied_publisher_autotest(self):
        # Publisher in auto-test mode is not allowed to create notficiation

        self.create_pub_acc(auto_test=True)
        notification = APIFactory.incoming_notification_dict()

        # Try CREATE_NOTIFICATION
        resp = self.partial_json_post("v4_api.create_notification", self.publisher_api_key)(data=json.dumps(notification))
        assert resp.status_code == 403
        # expect a special error message
        assert resp.json["error"] == "A publisher in auto-testing mode is not able to create notifications."

        # Try CREATE_NOTIFICATION_FROM_LIST
        notification_list = [{"notification": notification, "id": 1}]
        resp = self.partial_json_post("v4_api.create_notifications_from_list", self.publisher_api_key)(
            data=json.dumps(notification_list))
        assert resp.status_code == 403
        # expect a special error message
        assert resp.json["error"] == "A publisher in auto-testing mode is not able to create notifications."

    @app_decorator
    def test_create_and_get_notification(self):
        notification = APIFactory.incoming_notification_dict()

        resp = self.partial_json_post("v4_api.create_notification")(data=json.dumps(notification))
        assert resp.status_code == 201
        json_1 = resp.json
        id = json_1["id"]
        url = json_1["location"]    # URL is the calculated endpoint for retrieving the notification
        retrieved_response = self.test_client.get(url + '?api_key=' + ADMIN_API_KEY,)
        assert retrieved_response.status_code == 200
        assert retrieved_response.headers["content-type"] == "application/json"
        # Retrieved notification is an OutgoingNotification
        outgoing_json = retrieved_response.json
        assert outgoing_json["id"] == id
        assert outgoing_json["provider"]["agent"] == "Jisc Admin"  # Org-name of default admin account
        assert outgoing_json["links"] == [
            {"type": "splash", "format": "text/html", "url": "http://example.com/article/1", "access": "public"},
            {"type": "fulltext", "format": "application/pdf", "url": "http://example.com/article/1/pdf", "access": "public"}
        ]

        # Convert newly created unrouted notification (that was created via API) into a Routed notification
        UnroutedNotification.pull(id).make_routed().update()
        retrieved_response = self.test_client.get(url + '?api_key=' + ADMIN_API_KEY,)
        assert retrieved_response.status_code == 200
        outgoing_json = retrieved_response.json
        assert outgoing_json["id"] == id

    @staticmethod
    def _assert_v3_outoing(outgoing_note):
        assert isinstance(outgoing_note["id"], str)
        assert "created" not in outgoing_note  # v4 API has "created" instead of "created_date"
        assert "created_date" in outgoing_note  # v4 API has "created" instead of "created_date"
        assert "vers" not in outgoing_note
        md = outgoing_note["metadata"]
        assert "peer_reviewed" not in md
        assert "ack" not in md
        auth_0 = md["author"][0]
        assert "affiliations" not in auth_0  # Expect "affiliation" string NOT "affiliations" list
        assert "affiliation" in auth_0
        assert type(auth_0["affiliation"]) is str
        for link in outgoing_note["links"]:
            if link["access"] in ("router", "special"):
                assert "api/v3" in link["url"]

    @staticmethod
    def _assert_v4_outoing(outgoing_note, from_v4=False):
        """
        Confirm outgoing notification has particular expected fields.  If the source notification was created via v4
        then confirm it contains "peer_reviewed" & "ack" fields (these won't be present for V3 source).
        """
        assert isinstance(outgoing_note["id"], int)
        assert "created" in outgoing_note  # v4 API has "created" instead of "created_date"
        assert "vers" not in outgoing_note
        md = outgoing_note["metadata"]
        if from_v4:
            assert "peer_reviewed" in md
            assert "ack" in md
        auth_0 = md["author"][0]
        assert "affiliation" not in auth_0
        assert "affiliations" in auth_0  # Expect list of affiliations, each being a dict
        auth_0_affs = auth_0["affiliations"]
        assert type(auth_0_affs) is list
        assert type(auth_0_affs[0]) is dict
        for link in outgoing_note["links"]:
            if link["access"] in ("router", "special"):
                assert "api/v4" in link["url"]

    @app_decorator
    def test_v3_v4_post_get_notification_api(self):

        url_template = f"http://localhost/api/{{}}/notification{{}}?api_key={ADMIN_API_KEY}"

        ## 1 - Create notification via V3 API

        v3_note = APIFactory.incoming_notification_dict(note_vers="3")
        assert v3_note["vers"] == "3"

        # V3 notification has affilation string
        assert "affiliation" in v3_note["metadata"]["author"][0]
        assert type(v3_note["metadata"]["author"][0]["affiliation"]) is str

        resp = self.test_client.post(url_template.format("v3", ""),
                                     content_type="application/json",
                                     data=json.dumps(v3_note))
        assert resp.status_code == 201  # Created
        id = resp.json["id"]

        ## 1.0 - Confirm that notification record was created as a v4 notification (despite submitting v3 format)

        # Retrieve notification dict
        note_dict = UnroutedNotification.pull(id, wrap=False)

        # Check that notification was saved as latest version
        assert note_dict["vers"] == "4"
        assert "affiliation" not in note_dict["metadata"]["author"][0]
        assert "affiliations" in note_dict["metadata"]["author"][0]
        assert type(note_dict["metadata"]["author"][0]["affiliations"]) is list

        # confirm that v3 affiliation has been saved as {"raw": "...affiliation string..."}
        assert note_dict["metadata"]["author"][0]["affiliations"][0]["raw"] == v3_note["metadata"]["author"][0]["affiliation"]

        ## 1.1 - Retrieve v3 notification via V3 API - ensure it has expected structure for v3

        # Get using v3 API
        resp = self.test_client.get(url_template.format("v3", f"/{id}"))
        assert resp.status_code == 200

        # Check v3 fields
        self._assert_v3_outoing(resp.json)

        ## 1.2 - Retrieve v3 notification via V4 API - ensure it has expected structure for v4

        # Get notification using v4 API
        resp = self.test_client.get(url_template.format("v4", f"/{id}"))
        assert resp.status_code == 200

        # Check v4 fields
        self._assert_v4_outoing(resp.json)

        ## 2 - Create notification via V4 API

        v4_note = APIFactory.incoming_notification_dict(note_vers="4")
        assert v4_note["vers"] == "4"
        resp = self.test_client.post(url_template.format("v4", ""),
                                     content_type="application/json",
                                     data=json.dumps(v4_note))
        assert resp.status_code == 201  # Created
        id = resp.json["id"]

        ## 2.1 - Retrieve v4 notification via V3 API - ensure it has expected structure for v3

        # Get using v3 API
        resp = self.test_client.get(url_template.format("v3", f"/{id}"))
        assert resp.status_code == 200

        # Check v3 fields
        self._assert_v3_outoing(resp.json)

        ## 2.2 - Retrieve v4 notification via V4 API - ensure it has expected structure for v4

        # Get notification using v4 API
        resp = self.test_client.get(url_template.format("v4", f"/{id}"))
        assert resp.status_code == 200

        # Check v4 fields
        self._assert_v4_outoing(resp.json, True)

    @app_decorator
    def test_v3_v4_routed_api(self):
        """
        Test that returned notifications are as expected for V3 & V4 API calls to:
        * get routed
        * get notification/<id>
        """
        # setting since_id to 0 ensures all notifications are retrieved.
        url_template = f"http://localhost/api/{{}}/routed/{{}}?api_key={ADMIN_API_KEY}&{{}}"

        ## 1 - Create 2 routed notifications (one v3, the  other v4)

        # Create repository account
        repo_acc = AccountFactory.repo_account(org_name="Test Acc")

        # Create 2 notifications, one of each version
        for vers in ("3", "4"):
            note_dict = NotificationFactory.routed_notification(no_id_or_created=True, note_vers=vers)
            note = RoutedNotification(note_dict)
            note.repositories = [repo_acc.id]
            note.save_newly_routed()

        ## 2 - Check /routed endpoint V3 - against 2 routed notifications (one v3, the  other v4)

        # Get notification using v3 API
        resp = self.test_client.get(url_template.format("v3", repo_acc.uuid, "since=2000-01-01"))
        assert resp.status_code == 200
        j = resp.json
        assert j["since"] == "2000-01-01T00:00:00Z"
        assert "since_id" not in j
        assert j["total"] == 2
        for note in j["notifications"]:
            self._assert_v3_outoing(note)

        ## 3 - Check /routed endpoint V4 - against 2 routed notifications (one v3, the  other v4)

        # Get notification using v4 API
        resp = self.test_client.get(url_template.format("v4", repo_acc.uuid, "since_id=0"))
        assert resp.status_code == 200
        j = resp.json
        assert j["since"] == ""
        assert j["since_id"] == 0
        assert j["total"] == 2
        for note in j["notifications"]:
            self._assert_v4_outoing(note)

    @app_decorator
    def test_get_notification_fail(self):
        # ways in which the notification http request can fail
        # 1. invalid/wrong auth credentials
        # FIXME: we can't test for this yet

        # 2. invalid/not found notification id
        url = url_for("v4_api.retrieve_notification", notification_id="999", api_key=ADMIN_API_KEY)
        resp = self.test_client.get(url)
        assert resp.status_code == 404

    @app_decorator
    def test_get_store_content_inc_failures(self):
        notification = APIFactory.incoming_notification_dict(with_content=True)
        example_package = PackageFactory.example_package_path()
        partial_post = self.partial_post("v4_api.create_notification")
        resp = partial_post(data=self.create_file_dict(json.dumps(notification), example_package))
        loc = resp.json["location"]

        # Retrieve unrouted notification, then convert to routed notification because /content endpoint works only
        # for ROUTED notifications
        note_id = int(loc.rsplit("/", 1)[-1])
        unrouted = UnroutedNotification.pull(note_id)
        routed = unrouted.make_routed()
        routed.update()
        resp2 = self.test_client.get(f"{loc}/content?api_key={ADMIN_API_KEY}")
        assert resp2.status_code == 200

        # INVALID API Key
        resp2 = self.test_client.get(f"{loc}/content?api_key={INVALID_API_KEY}")
        assert resp2.status_code == 401

        # INVALID NOTE ID
        resp3 = self.test_client.get(f"{999}/content?api_key={ADMIN_API_KEY}")
        assert resp3.status_code == 404

    @app_decorator
    def test_get_content_fail(self):
        # ways in which the content http request can fail
        # invalid/not found notification id
        url = url_for("v4_api.retrieve_content", notification_id="123123", filename="1", api_key=ADMIN_API_KEY)
        resp = self.test_client.get(url)
        assert resp.status_code == 404

    @app_decorator
    def test_list_notifications_for_repository(self):
        # Create repository account
        repo_acc = AccountFactory.repo_account(org_name="Test Acc")

        # Create 3 notifications for - 2 will be associated with repo_acc, 1 will not (it will be associated with
        # fictitious account ID 999); remove "id" & "created" elements.
        note_dict = NotificationFactory.routed_notification(no_id_or_created=True)
        saved_note_ids = []
        for x in range(3):
            note_dict["metadata"]["article"]["title"] = f"Test Notification #{x}"
            note = RoutedNotification(note_dict)
            # For the first notification (x == 0) set repo-id to 999 (non-existant) otherwise to ID of repo_acc
            note.repositories = [repo_acc.id if x else 999]
            note.save_newly_routed()
            saved_note_ids.append(note.id)    # The act of saving, will generate (ascending) ID values

        ## Test as Admin user specifying the repo_uuid - expect 2 notifications
        print("\n* 1 *")
        url = url_for(
            "v4_api.list_repository_routed",
            repo_uuid=repo_acc.uuid,
            api_key=ADMIN_API_KEY,
            since="2001-01-01T00:00:00Z",
            page="1",
            pageSize="67"
        )
        resp = self.test_client.get(url)
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/json"
        j = resp.json
        assert j["since"] == "2001-01-01T00:00:00Z"
        assert j["page"] == 1
        assert j["pageSize"] == 67
        assert "timestamp" in j
        assert j["total"] == 2
        assert "notifications" in j
        for x in range(2):
            assert j["notifications"][x]["metadata"]["article"]["title"] == f"Test Notification #{x + 1}"

        ## Test Using repo_acc API-Key WIHTOUT specifying the repo_uuid - expect 2 notifications
        print("\n* 2 *")
        url = url_for(
            "v4_api.list_repository_routed",
            api_key=repo_acc.api_key,
            since="2001-01-01T00:00:00Z",
            page="1",
            pageSize="67"
        )
        resp = self.test_client.get(url)
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/json"
        j = resp.json
        assert j["since"] == "2001-01-01T00:00:00Z"
        assert j["page"] == 1
        assert j["pageSize"] == 67
        assert "timestamp" in j
        assert j["total"] == 2
        assert "notifications" in j
        for x in range(2):
            assert j["notifications"][x]["metadata"]["article"]["title"] == f"Test Notification #{x + 1}"

        ## As Repo_acc user - Test retrieving 2nd page (expect no notifications)
        print("\n* 3 *")
        url = url_for(
            "v4_api.list_repository_routed",
            repo_uuid=repo_acc.uuid,
            api_key=ADMIN_API_KEY,
            since="2001-01-01T00:00:00Z",
            page="2",
            pageSize="10"
        )
        resp = self.test_client.get(url)
        assert resp.status_code == 200
        j = resp.json
        assert j["page"] == 2
        assert j["pageSize"] == 10
        assert j["total"] == 2     # There are 2 notifications
        assert j["notifications"] == []     # No notifications for Page 2

        ## As repo_acc  user Test with pageSize of 1, get 2nd page - expect 1 notification
        print("\n* 4 *")
        url = url_for(
            "v4_api.list_repository_routed",
            api_key=repo_acc.api_key,
            since="2001-01-01T00:00:00Z",
            page="2",
            pageSize="1"
        )
        resp = self.test_client.get(url)
        assert resp.status_code == 200
        j = resp.json
        assert j["page"] == 2
        assert j["pageSize"] == 1
        assert j["total"] == 2     # There are 2 notifications
        assert len(j["notifications"]) == 1     # With pagesize of 1, expect 2nd page to have 2 notification

        ## Test retrieval using since_id (instead of since date) - Use 0 as ID - should return all notfications for the
        ## Repo account
        print("\n* 5 *")
        url = url_for(
            "v4_api.list_repository_routed",
            api_key=repo_acc.api_key,
            since_id=0,     # All IDs should be greater than this
            page="1",
            pageSize="10"
        )
        resp = self.test_client.get(url)
        assert resp.status_code == 200
        j = resp.json
        assert j["page"] == 1
        assert j["pageSize"] == 10
        assert j["since"] == ""
        assert j["since_id"] == 0
        assert j["total"] == 2     # There are 2 notifications (associated with this repo)
        assert len(j["notifications"]) == 2

        ## Test retrieval using since_id (instead of since date) - Use last ID created - there should be NO notifications
        ## with an ID greater than that
        print("\n* 6 *")
        url = url_for(
            "v4_api.list_repository_routed",
            api_key=repo_acc.api_key,
            since_id=saved_note_ids[2],     # The ID of last notification - there should be no IDs greater than this
            page="1",
            pageSize="10"
        )
        resp = self.test_client.get(url)
        assert resp.status_code == 200
        j = resp.json
        assert j["since_id"] == saved_note_ids[2]
        assert j["total"] == 0     # There are 0 notifications
        assert len(j["notifications"]) == 0

        ## Test retrieval using since_id (instead of since date) - Use penultimate ID created - there should be
        ## 1 notification with an ID greater than that
        print("\n* 7 *")
        url = url_for(
            "v4_api.list_repository_routed",
            api_key=repo_acc.api_key,
            since_id=saved_note_ids[1],     # The ID of penultimate notification - there should be 1 ID greater than this
            page="1",
            pageSize="10"
        )
        resp = self.test_client.get(url)
        assert resp.status_code == 200
        j = resp.json
        assert j["since_id"] == saved_note_ids[1]
        assert j["total"] == 1
        assert len(j["notifications"]) == 1

    @app_decorator
    def test_get_list_repository_fail(self):
        # ways in which the list repository http request can fail

        ## No repo_uuid
        url_partial = partial(url_for, "v4_api.list_repository_routed", api_key=ADMIN_API_KEY)
        resp = self.test_client.get(url_partial())
        assert resp.status_code == 400, resp.status_code
        assert resp.headers["content-type"] == "application/json"
        j = resp.json
        assert "error" in j
        assert j["error"] == "A repository account UUID must be provided."

        ## Bad repo_uuid (account doesn't exist)
        url_partial = partial(url_for, "v4_api.list_repository_routed", api_key=ADMIN_API_KEY, repo_uuid="999")
        resp = self.test_client.get(url_partial())
        assert resp.status_code == 404, resp.status_code
        assert resp.headers["content-type"] == "application/json"
        j = resp.json
        assert "error" in j
        assert j["error"] == "No repository account with UUID: 999."

        # Create repository account
        repo_acc = AccountFactory.repo_account(org_name="Test Acc")

        # repo_uuid does NOT match the uuid of the Account
        url_partial = partial(url_for, "v4_api.list_repository_routed", api_key=repo_acc.api_key, repo_uuid="WRONG-UUID")
        resp = self.test_client.get(url_partial())
        assert resp.status_code == 403, resp.status_code
        assert resp.headers["content-type"] == "application/json"
        j = resp.json
        assert "error" in j
        assert j["error"] == f"You may only retrieve notifications for repository id: {repo_acc.uuid}."

        # Neither Since date nor since_id is provided
        url_partial = partial(url_for, "v4_api.list_repository_routed", api_key=ADMIN_API_KEY, repo_uuid=repo_acc.uuid)
        resp = self.test_client.get(url_partial())
        assert resp.status_code == 400, resp.status_code
        assert resp.headers["content-type"] == "application/json"
        j = resp.json
        assert "error" in j
        assert j["error"] == "Missing required parameter 'since' (date-time) or 'since_id'"

        # Since_id parameter is NOT an integer)
        url = url_partial(since_id="Not number")
        resp = self.test_client.get(url)
        assert resp.status_code == 400
        assert resp.headers["content-type"] == "application/json"
        j = resp.json
        assert "error" in j
        assert j["error"] == "Parameter 'since_id' is not an integer"

        # Since parameter wrongly formatted
        url = url_partial(since="wednesday")
        resp = self.test_client.get(url)
        assert resp.status_code == 400
        assert resp.headers["content-type"] == "application/json"
        j = resp.json
        assert "error" in j
        assert j["error"] == "Unable to understand since date 'wednesday'"

        # page/pageSize parameters wrongly formatted
        url = url_partial(since="2001-01-01T00:00:00Z", page="0", pageSize="25")
        resp = self.test_client.get(url)
        assert resp.status_code == 400
        assert resp.headers["content-type"] == "application/json"
        j = resp.json
        assert "error" in j
        assert j["error"] == "Parameter 'page' must be greater than or equal to 1"

        url = url_partial(since="2001-01-01T00:00:00Z", page="first", pageSize="25")
        resp = self.test_client.get(url)
        assert resp.status_code == 400
        assert resp.headers["content-type"] == "application/json"
        j = resp.json
        assert "error" in j
        assert j["error"] == "Parameter 'page' is not an integer"

        url = url_partial(since="2001-01-01T00:00:00Z", page="1", pageSize="10000000")
        resp = self.test_client.get(url)
        assert resp.status_code == 400
        assert resp.headers["content-type"] == "application/json"
        j = resp.json
        assert "error" in j
        assert j["error"] == "Parameter pageSize must be between 1 and 100"

        url = url_partial(since="2001-01-01T00:00:00Z", page="1", pageSize="loads")
        resp = self.test_client.get(url)
        assert resp.status_code == 400
        assert resp.headers["content-type"] == "application/json"
        j = resp.json
        assert "error" in j
        assert j["error"] == "Parameter 'pageSize' is not an integer"

    @app_decorator
    def test_fail_create_notification_list_first_item_empty(self):
        # check that when the first item in the list is invalid - we get a 202
        bad_notification = [{"notification": {}, "id": 1}]

        resp = self.partial_json_post("v4_api.create_notifications_from_list")(data=json.dumps(bad_notification))
        assert resp.status_code == 400
        assert "JSON object did not contain a notification" in resp.json.get("error")

    @app_decorator
    def test_fail_create_notification_list_first_item_garbage(self):
        # check that when the first item in the list is total garbage (not just "invalid") that we get 400s back
        bad_notification = [{"notification": "This is a string.", "id": 1}]

        resp = self.partial_json_post("v4_api.create_notifications_from_list")(data=json.dumps(bad_notification))
        assert resp.status_code == 400
        error = resp.json.get("error")
        assert "A notification in the list is not a JSON object" in error
        assert "REQUEST_ID: 1" in error

        bad_notification = ["garbage"]

        resp = self.partial_json_post("v4_api.create_notifications_from_list")(data=json.dumps(bad_notification))
        assert resp.status_code == 400
        error = resp.json.get("error")
        assert "A notification in the list is not a JSON object" in error
        assert "REQUEST_ID" not in error

        # and test with a string representation of a json object
        notification = APIFactory.incoming_notification_dict()
        # string notification instead of json
        notification_list = [{"notification": json.dumps(notification), "id": 99}]

        resp = self.partial_json_post("v4_api.create_notifications_from_list")(data=json.dumps(notification_list))
        assert resp.status_code == 400
        error = resp.json.get("error")
        assert "A notification in the list is not a JSON object" in error
        assert "REQUEST_ID: 99" in error

    @app_decorator
    def test_ok_create_notification_list(self):
        notification = APIFactory.incoming_notification_dict()
        notification_list = [{"notification": notification, "id": 1}]

        # make the request as a publisher
        self.create_pub_acc()
        resp = self.partial_json_post("v4_api.create_notifications_from_list", self.publisher_api_key)(data=json.dumps(notification_list))
        j = resp.json

        assert resp.status_code == 201
        assert j.get("successful") == 1
        assert j.get("total") == 1
        # check that only one deposit record was produced
        assert self.deposit_record_stats() == (1, 1, 0)

        # make the request as an admin again
        self.partial_json_post("v4_api.create_notifications_from_list")(data=json.dumps(notification_list))
        # check that deposit records have not changed
        assert self.deposit_record_stats() == (1, 1, 0)

    @app_decorator
    def test_fail_no_list_create_notification_list(self):
        notification_list = ""

        resp = self.partial_json_post("v4_api.create_notifications_from_list")(data=json.dumps(notification_list))

        assert resp.status_code == 400
        # check that deposit records were not produced
        assert self.deposit_record_stats() == (0, 0, 0)

    @app_decorator
    def test_fail_with_xml_create_notification_list(self):
        # check that when we pass xml we get a 400
        resp = self.partial_json_post("v4_api.create_notifications_from_list")(data="<xml></xml>")
        assert resp.status_code == 400
        # check that deposit records were not produced
        assert self.deposit_record_stats() == (0, 0, 0)

    @app_decorator
    def test_not_a_list_create_notification_list(self):
        # check that when we pass something which isn't a list to the create_notifications_from_list
        # endpoint, we get a 400 back
        resp = self.partial_post("v4_api.create_notifications_from_list")(data="{}")
        assert resp.status_code == 400
        # check that deposit records were not produced
        assert self.deposit_record_stats() == (0, 0, 0)

    @app_decorator
    def test_some_fails_create_notification_list(self):
        # check the behaviour is as expected when some notifications succeed and others fail
        notification = APIFactory.incoming_notification_dict()
        bad_notification = {}
        notification_list = [{"notification": notification, "id": 'a'},
                             {"notification": bad_notification, "id": 'b'},
                             {"notification": bad_notification, "id": 'c'},
                             None,
                             {"notification": notification, "id": 'e'}]
        # make the request as a publisher
        self.create_pub_acc()
        resp = self.partial_json_post("v4_api.create_notifications_from_list", self.publisher_api_key)(data=json.dumps(notification_list))
        j = resp.json
        assert resp.status_code == 202
        assert j.get("successful") == 2
        assert j.get("total") == 5
        # check that deposit records were produced for each of the notifications
        assert self.deposit_record_stats() == (5, 2, 3)

        notification = APIFactory.incoming_notification_dict()
        bad_notification = {}
        notification_list = [{"notification": notification, "id": "1"},
                             {"notification": bad_notification, "id": 2},
                             {"notification": notification},
                             {"notification": bad_notification},
                             None,
                             {"notification": notification, "id": 6}]
        # make this request as an admin
        resp = self.partial_json_post("v4_api.create_notifications_from_list")(data=json.dumps(notification_list))
        j = resp.json
        assert resp.status_code == 202
        assert j.get("successful") == 2
        assert j.get("total") == 6

        # check that deposit records were not produced for each of the notifications (as this was an admin user)
        assert self.deposit_record_stats() == (5, 2, 3)

    @app_decorator
    def test_validate_list(self):
        notification = APIFactory.incoming_notification_dict(good_affs=True, no_links=True)
        notification_list = [{"notification": notification, "id": 1}]
        self.create_pub_acc()
        partial_validate_post = self.partial_json_post("v4_api.validate_list", self.publisher_api_key)

        resp = partial_validate_post(data=json.dumps(notification_list))
        assert resp.status_code == 200

        resp = partial_validate_post(data=json.dumps([]))
        assert resp.status_code == 200

    @app_decorator
    def test_validate_list_fail(self):
        notification = APIFactory.incoming_notification_dict()
        # no id
        notification_list = [{"notification": notification}]

        self.create_pub_acc()
        partial_validate_post = self.partial_json_post("v4_api.validate_list", self.publisher_api_key)

        resp = partial_validate_post(data=json.dumps(notification_list))
        assert resp.status_code == 400

        resp = partial_validate_post(data=json.dumps(["Not an object"]))
        assert resp.status_code == 400

    @app_decorator
    def test_search_identifiers(self):
        identifier = IdentifierFactory.make_jisc("University of Something")

        resp = self.test_client.get(
            url_for("admin.search_identifiers", name="University", type="JISC", api_key=ADMIN_API_KEY)
        )

        assert resp.status_code == 200

        j = resp.json
        assert j
        assert j[0] == {
            "id": identifier.value,
            "institution": identifier.name,
            "type": "JISC"
        }

    @app_decorator
    def test_api_key_wildcarding_not_allowed(self):
        response = self.test_client.get(url_for("admin.search_identifiers", name="Anything", api_key=ADMIN_API_KEY))
        assert response.status_code == 200

        # This should return a 401
        part_key = ADMIN_API_KEY[0:2] + "*"
        response = self.test_client.get(url_for("admin.search_identifiers", name="Anything", api_key=part_key))
        assert response.status_code == 401

    @app_decorator
    def test_matching_params_success(self):
        # full post through get successful
        repo_acc = AccountFactory.repo_account(live=True)
        rep_conf = RepositoryFactory.repo_config()
        # Submission config contains spaces within the ORG ids (these are expected to be stripped out)
        submission_config = RepositoryFactory.repo_config(spaces_in_org_ids=True)
        # TEST ADMIN submits config (MUST provide repo_id)
        resp = self.test_client.post(
            url_for("v4_api.config", api_key=ADMIN_API_KEY, repo_uuid=repo_acc.uuid),
            content_type="application/json",
            data=json.dumps(submission_config)
        )
        assert resp.status_code == 204

        # test that getting match params is working
        resp = self.test_client.get(url_for("v4_api.config", repo_uuid=repo_acc.uuid, api_key=ADMIN_API_KEY))
        j = resp.json
        assert resp.status_code == 200
        # check that the configs are the same
        assert set(rep_conf["domains"]) == set(j["domains"])
        assert set(rep_conf["name_variants"]) == set(j["name_variants"])
        assert set(rep_conf["postcodes"]) == set(j["postcodes"])
        assert set(rep_conf["grants"]) == set(j["grants"])
        assert set(rep_conf["org_ids"]) == set(j["org_ids"])
        assert set(rep_conf["orcids"]) == set(j["orcids"])

        # Now update ORCIDS only
        submission_config = {"orcids": ["1111-2222-3333-4444", "aaaa-bbbb-cccc-dddd"]}
        # TEST ADMIN submits config (MUST provide repo_id)
        self.test_client.post(
            url_for("v4_api.config", api_key=ADMIN_API_KEY, repo_uuid=repo_acc.uuid),
            content_type="application/json",
            data=json.dumps(submission_config)
        )
        # Confirm that ONLY the ORCIDS have changed
        resp = self.test_client.get(url_for("v4_api.config", repo_uuid=repo_acc.uuid, api_key=ADMIN_API_KEY))
        j = resp.json
        assert resp.status_code == 200
        assert set(rep_conf["domains"]) == set(j["domains"])
        assert set(rep_conf["name_variants"]) == set(j["name_variants"])
        assert set(rep_conf["postcodes"]) == set(j["postcodes"])
        assert set(rep_conf["grants"]) == set(j["grants"])
        assert set(rep_conf["org_ids"]) == set(j["org_ids"])
        assert set(submission_config["orcids"]) == set(j["orcids"])

        # TEST REPO user submits config (must NOT provide the repo_id)
        resp = self.test_client.post(
            url_for("v4_api.config", api_key=repo_acc.api_key),
            content_type="application/json",
            data=json.dumps(submission_config)
        )
        assert resp.status_code == 204

        # test that getting match params is working
        resp = self.test_client.get(url_for("v4_api.config", api_key=repo_acc.api_key))
        j = resp.json
        assert resp.status_code == 200
        # check that the configs are the same
        assert set(rep_conf["domains"]) == set(j["domains"])
        assert set(rep_conf["name_variants"]) == set(j["name_variants"])
        assert set(rep_conf["postcodes"]) == set(j["postcodes"])
        assert set(rep_conf["grants"]) == set(j["grants"])
        assert set(rep_conf["org_ids"]) == set(j["org_ids"])

    @app_decorator
    def test_matching_params_unsuccessful_post(self):
        # unsuccessful post request due to invalid content
        repo_acc = AccountFactory.repo_account(live=True)
        invalid_config = RepositoryFactory.invalid_repo_config()

        # TEST ADMIN submits invalid config (MUST provide repo_id)
        resp = self.test_client.post(
            url_for("v4_api.config", api_key=ADMIN_API_KEY, repo_uuid=repo_acc.uuid),
            content_type="application/json",
            data=json.dumps(invalid_config)
        )
        assert resp.status_code == 400
        assert resp.json["error"] == "Invalid content in matching parameters (no changes were made)."

        # TEST ADMIN submits NO config (MUST provide repo_id)
        resp = self.test_client.post(
            url_for("v4_api.config", api_key=ADMIN_API_KEY, repo_uuid=repo_acc.uuid)
        )
        assert resp.status_code == 400
        assert resp.json["error"] == "Problem setting matching parameters - ensure you submit valid data."

        # TEST REPO user submits invalid config (must NOT provide the repo_id)
        resp = self.test_client.post(
            url_for("v4_api.config", api_key=repo_acc.api_key),
            content_type="application/json",
            data=json.dumps(invalid_config)
        )
        assert resp.status_code == 400
        # expect a special error message
        assert resp.json["error"] == "Invalid content in matching parameters (no changes were made)."

        # TEST REPO user submits NO config (must NOT provide the repo_id)
        resp = self.test_client.post(
            url_for("v4_api.config", api_key=repo_acc.api_key)
        )
        assert resp.status_code == 400
        assert resp.json["error"] == "Problem setting matching parameters - ensure you submit valid data."

    @app_decorator
    def test_matching_params_admin_no_repoid(self):
        # unsuccessful post request due admin user but no repo-id specified
        rep_conf = RepositoryFactory.repo_config()
        # TEST ADMIN submits config (MUST provide repo_id)
        resp = self.test_client.post(
            url_for("v4_api.config", api_key=ADMIN_API_KEY, repo_uuid=None),
            content_type="application/json",
            data=json.dumps(rep_conf)
        )
        assert resp.status_code == 400
        # expect a special error message
        assert resp.json["error"] == "A repository UUID must be provided."

    @app_decorator
    def test_matching_params_forbidden(self):
        # Repo account specifies an ID; Publisher attempts to access endpoint
        repo_acc = AccountFactory.repo_account(live=True)
        rep_conf = RepositoryFactory.repo_config()

        # TEST Repository wrongly specifies a repo_id
        resp = self.test_client.post(
            url_for("v4_api.config", api_key=repo_acc.api_key, repo_uuid="BAD-UUID"),
            content_type="application/json",
            data=json.dumps(rep_conf)
        )
        assert resp.status_code == 403
        # expect a special error message
        assert resp.json["error"] == "You are not authorised to access account: BAD-UUID."

        # TEST Publisher attemts to use endpoint
        pub_acc = AccountFactory.publisher_account()
        resp = self.test_client.post(
            url_for("v4_api.config", api_key=pub_acc.api_key, repo_uuid=repo_acc.uuid),
            content_type="application/json",
            data=json.dumps(rep_conf)
        )
        assert resp.status_code == 403
        # expect a special error message
        assert resp.json["error"] == "Only an admin or repository user can access this endpoint."
