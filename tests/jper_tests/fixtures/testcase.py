"""
An implementation of TestCase for JPER

Simply uses octopus.modules.store.store.StoreLocal as the store implementation (to avoid using the live one) and
gives access to decorators that redirect any JPER related request to the flask test client
(so we don't need a running JPER server.)
"""
# http://requests-mock.readthedocs.io/en/latest/overview.html
import os
import shutil

from flask import current_app
from tests.fixtures.testcase import JPERMySQLTestCase
from router.jper.app import app_decorator, app

app.config["TESTING"] = True

from tests.jper_tests.fixtures.security_gui import blueprint as security_gui_blueprint
from tests.jper_tests.fixtures.security_api import blueprint as security_api_blueprint


# This must ONLY be run once, and before any tests are run. This is because pytest doesn't re-import modules, so we
# cannot register the security blueprint at a later time, as the state of the Flask app after a test that uses a
# request will block the blueprint from being registered.
app.register_blueprint(security_gui_blueprint, url_prefix="/security_gui")
app.register_blueprint(security_api_blueprint, url_prefix="/security_api")


def safe_makedirs(path):
    os.makedirs(path, exist_ok=True)


class JPERTestCase(JPERMySQLTestCase):

    test_client = None
    # Use os.path.join to make sure that these paths are correct on Windows
    store = os.path.join("/tmp", "store")
    ftp = os.path.join("/tmp", "ftp")
    reports = os.path.join("/tmp", "reports")

    @classmethod
    def store_path(cls, endpoint):
        return os.path.join(cls.store, endpoint)

    @classmethod
    def ftp_path(cls, endpoint):
        return os.path.join(cls.ftp, endpoint)

    @classmethod
    def report_path(cls, endpoint):
        return os.path.join(cls.reports, endpoint)

    @classmethod
    def setup_store(cls):
        # Set up store directories
        shutil.rmtree(cls.store, ignore_errors=True)
        safe_makedirs(current_app.config["STORE_TMP_DIR"])
        safe_makedirs(current_app.config["STORE_MAIN_DIR"])

    @classmethod
    def setup_ftp(cls):
        # Set up FTP related directories
        shutil.rmtree(cls.ftp, ignore_errors=True)
        safe_makedirs(current_app.config["FTP_SAFETY_DIR"])
        safe_makedirs(current_app.config["USERDIR"])
        safe_makedirs(current_app.config["FTP_TMP_DIR"])

    @classmethod
    def setup_reports(cls):
        # Set up reports directory
        shutil.rmtree(cls.reports, ignore_errors=True)
        safe_makedirs(current_app.config["REPORTSDIR"])

    @classmethod
    @app_decorator
    def setUpClass(cls):
        """
        Set up flask settings to make sure we use temporary file locations.
        """
        # JPERMySQLTestCase.setUpClass()

        super().setUpClass()
        # Use localhost and http for simplicity
        scheme = "http"
        server = "localhost"
        curr_app_config = current_app.config  # Do this to avoid repeatedly calling current_app local-proxy

        curr_app_config["PREFERRED_URL_SCHEME"] = scheme
        curr_app_config["SERVER_NAME"] = server
        base_url = f'{scheme}://{server}/'
        curr_app_config["BASE_URL"] = base_url
        curr_app_config["JPER_BASE_URL"] = f'{base_url}api/v4'
        curr_app_config["API_NOTE_URL_TEMPLATE"] = f'{base_url}api/v{{}}/notification/{{}}'

        # Set up store
        curr_app_config["STORE_TMP_DIR"] = cls.store_path("tmp")
        curr_app_config["STORE_MAIN_DIR"] = cls.store_path("live")
        curr_app_config["STORE_TYPE"] = None  # Force StoreFactory to use STORE_IMPL
        curr_app_config["STORE_IMPL"] = "octopus.modules.store.store.StoreLocal"
        # Set up FTP related paths
        curr_app_config["FTP_TMP_DIR"] = cls.ftp_path("ftptmp")
        curr_app_config["USERDIR"] = cls.ftp_path("sftpusers")
        curr_app_config["FTP_SAFETY_DIR"] = cls.ftp_path("safety")
        # set up reports
        curr_app_config["REPORTSDIR"] = cls.reports
        # Disable FTP accounts on UNIX
        curr_app_config["UNIX_FTP_ACCOUNT_ENABLE"] = False

        cls.test_client = current_app.test_client()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        # Clear all folders
        shutil.rmtree(cls.reports, ignore_errors=True)
        shutil.rmtree(cls.ftp, ignore_errors=True)
        shutil.rmtree(cls.store, ignore_errors=True)

    @app_decorator
    def setUp(self):
        super().setUp()
        current_app.config["STORE_IMPL"] = "octopus.modules.store.store.StoreLocal"
        # Set up all directories and add test client
        self.setup_ftp()
        self.setup_store()
        self.setup_reports()
        # self.test_client = current_app.test_client()

    def tearDown(self):
        super().tearDown()

    @staticmethod
    def in_list_comparison(list_expected, result_list):
        """
        For each entry in list_expected, confirms that it is found within an entry in result_list

        :param list_expected: List containing expected items - normally these are strings, but where an expected item
                        contains parts that may be in random order then this can be a tuple:
                        ("significant part which uniquely matches expected string", ["list", "of", "variable", "parts"])
                        In this case the members of the tuple[1] list must appear in the result as well as the
                        significant part.
        :param result_list: list to check against
        :return: True if all in list_expected are found in result_list, or  False if not
        """
        print("\n")
        all_ok = len(list_expected) == len(result_list)
        if all_ok:
            result_list_cpy = result_list.copy()
            expected_not_matched = []
            for expected in list_expected:
                if isinstance(expected, tuple):
                    variable_parts = expected[1]
                    expected = expected[0]
                else:
                    variable_parts = []
                ok = False
                for ix, result in enumerate(result_list_cpy):
                    if expected in result:
                        ok = True
                        for var_part in variable_parts:
                            if var_part not in result:
                                ok = False
                                break
                        if ok:
                            result_list_cpy.pop(ix)
                        break
                if not ok:
                    expected_not_matched.append(expected + (" ['" + "', '".join(variable_parts) + "']" if variable_parts else ""))
                    all_ok = False
            if not all_ok:
                if expected_not_matched:
                    print("--- The following Expected values were not found in validation results:\n    --",
                          "\n    -- ".join(expected_not_matched))
                if result_list_cpy:
                    print("--- The following validation results were not matched to expected results:\n    --",
                          "\n    -- ".join(result_list_cpy))
        return all_ok

