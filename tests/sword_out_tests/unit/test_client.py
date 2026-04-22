"""
Tests on the JPER client
"""

from router.jper_sword_out.app import app_decorator, app

from octopus.lib import http
from router.shared import client
from router.shared.models import note as note_models
from tests.fixtures.testcase import JPERMySQLTestCase
from tests.sword_out_tests.fixtures.notifications import NotificationFactory
import urllib.parse, json


def mock_list(url, *args, **kwargs):
    """
    Return list of mock notifications.
    Uses the `since` date to determine the number of notifications returned or whether an error should be simulated.
    """
    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query)

    since = params["since"][0]
    try:
        page = int(params["page"][0])
    except:
        page = None
    page_size = int(params["pageSize"][0]) if "pageSize" in params else None

    if since == "1970-01-01T00:00:00Z":
        # Return 2 notifications (for page 1 by default)
        nl = NotificationFactory.notification_list(since, page_size=2, total_recs=2)
        return http.MockResponse(200, json.dumps(nl))
    elif since == "1971-01-01T00:00:00Z":
        # Cause 3 notifications to be returned in the notification list
        num_results_before_current_page = (page - 1) * page_size if page else 0
        nl = NotificationFactory.notification_list(since,
                                                   page=page,
                                                   page_size=page_size,
                                                   # set toral_recs, so 3 results will be returned for current pg
                                                   total_recs=num_results_before_current_page + 3)
        return http.MockResponse(200, json.dumps(nl))
    elif since == "1972-01-01T00:00:00Z":
        return None
    elif since == "1973-01-01T00:00:00Z":
        return http.MockResponse(401)
    elif since == "1974-01-01T00:00:00Z":
        err = NotificationFactory.error_response()
        return http.MockResponse(400, json.dumps(err))

def mock_get_content(url, *args, **kwargs):
    parsed = urllib.parse.urlparse(url)

    if parsed.path.endswith("/content"):
        return http.MockResponse(200, "default content"), "", 0
    elif parsed.path.endswith("/content/ArticleFilesJATS.zip"):
        return http.MockResponse(200, "simplezip"), "", 0
    elif parsed.path.endswith("nohttp"):
        return None, "", 0
    elif parsed.path.endswith("auth"):
        return http.MockResponse(401), "", 0
    elif parsed.path.endswith("error"):
        err = NotificationFactory.error_response()
        return http.MockResponse(400, json.dumps(err)), "", 0

def mock_iterate(url, *args, **kwargs):
    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query)

    since = params["since"][0]
    try:
        page = int(params["page"][0])
    except:
        page = None
    if page == 1:
        nl = NotificationFactory.notification_list(since, page=page, page_size=2, total_recs=4, ids=[1111, 2222])
        return http.MockResponse(200, json.dumps(nl))
    elif page == 2:
        nl = NotificationFactory.notification_list(since, page=page, page_size=2, total_recs=4, ids=[3333, 4444])
        return http.MockResponse(200, json.dumps(nl))
    raise Exception()

API_KEY = "testing"
JPER_BASE_URL = "http://localhost:5024"

class TestClient(JPERMySQLTestCase):

    @classmethod
    @app_decorator
    def setUpClass(cls):
        # List the tables (by table name) needed for testing
        cls.tables_for_testing = ['account', 'acc_user', 'notification', 'notification_account']

        super(TestClient, cls).setUpClass()
        app.config["LOGFILE"] = "/tmp/sword-out-tests.log"

    @app_decorator
    def setUp(self):
        super(TestClient, self).setUp()

        self.old_http_get = http.get
        self.old_http_get_stream = http.get_stream

    @app_decorator
    def tearDown(self):
        super(TestClient, self).tearDown()

        http.get = self.old_http_get
        http.get_stream = self.old_http_get_stream

    @app_decorator
    def test_01_list_notifications(self):
        # specify the mock for the http.get function
        http.get = mock_list

        # create a client we can use
        c = client.JPER(api_key=API_KEY, base_url=JPER_BASE_URL)

        # first try with just a since date
        notes = c.list_routed_outgoing_notes("1970-01-01")
        assert len(notes.outgoing_notes) == 2
        assert notes.since == "1970-01-01T00:00:00Z"

        # now try with all the other parameters
        notes = c.list_routed_outgoing_notes("1971-01-01T00:00:00Z", page=5, page_size=100, repo_uuid="12345")
        assert notes.since == "1971-01-01T00:00:00Z"
        assert notes.page == 5
        assert notes.page_size == 100
        assert len(notes.outgoing_notes) == 3

        # check a failed http request
        with self.assertRaises(client.JPERConnectionException):
            notes = c.list_routed_outgoing_notes("1972-01-01")

        # failed auth
        with self.assertRaises(client.JPERAuthException):
            notes = c.list_routed_outgoing_notes("1973-01-01")

        # an error
        with self.assertRaises(client.JPERException):
            notes = c.list_routed_outgoing_notes("1974-01-01", page="forty")

    @app_decorator
    def test_02_get_content(self):
        # specify the mock for the http.get function
        http.get_stream = mock_get_content

        # create a client we can use
        c = client.JPER(api_key=API_KEY, base_url=JPER_BASE_URL)

        # try the default content url
        url = "http://localhost:5024/notification/12345/content"
        gen, headers = c.get_content(url)
        assert next(gen) == "default content"

        # try a specific content url
        url = "http://localhost:5024/notification/12345/content/ArticleFilesJATS.zip"
        gen, headers = c.get_content(url)
        assert next(gen) == "simplezip"

        # check a failed http request
        with self.assertRaises(client.JPERConnectionException):
            notes = c.get_content("/nohttp")

        # failed auth
        with self.assertRaises(client.JPERAuthException):
            notes = c.get_content("/auth")

        # an error
        with self.assertRaises(client.JPERException):
            notes = c.get_content("/error")

    @app_decorator
    def test_03_iterate_notifications(self):
        # specify the mock for the http.get function
        http.get = mock_iterate

        # create a client we can use
        c = client.JPER(api_key=API_KEY, base_url=JPER_BASE_URL)

        ids = []
        for note in c.iterate_routed_outgoing_notes("1970-01-01T00:00:00Z", repo_uuid=345, page_size=2):
            assert isinstance(note, note_models.OutgoingNotification)
            ids.append(note.id)

        assert ids == [1111, 2222, 3333, 4444]

    @app_decorator
    def test_04_notification_package_link(self):
        note = NotificationFactory.outgoing_notification()
        # try getting the two link types we know are in the notification
        faj = note.get_package_link("https://pubrouter.jisc.ac.uk/FilesAndJATS")
        assert faj is not None
        assert faj.get("url") == app.config["API_NOTE_URL_TEMPLATE"].format(4, 1234) + "/content"

        sz = note.get_package_link("http://purl.org/net/sword/package/SimpleZip")
        assert sz is not None
        assert sz.get("url") == app.config["API_NOTE_URL_TEMPLATE"].format(4, 1234) + "/content/ArticleFilesJATS.zip"

        # try getting a link which doesn't exist
        nx = note.get_package_link("http://some.package/or/other")
        assert nx is None
