import shutil
import os
from flask import current_app
from octopus.modules.store import store
from tests.fixtures.testcase import JPERMySQLTestCase

class SwordOutTestCase(JPERMySQLTestCase):

    # Use os.path.join to make sure that these paths are correct on Windows
    store = os.path.join("/tmp", "store")
    storage_mgr = None

    @classmethod
    def store_path(cls, endpoint):
        return os.path.join(cls.store, endpoint)

    @classmethod
    def setUpClass(cls):
        """
        Set up flask settings to make sure we use temporary file locations.
        """
        # List the tables (by table name) needed for testing
        cls.tables_for_testing = ['account', 'acc_user', 'notification', 'notification_account', 'sword_deposit']
        super().setUpClass()

        # Set up store
        curr_app_config = current_app.config  # Do this to avoid repeatedly calling current_app local-proxy
        curr_app_config["STORE_TMP_DIR"] = cls.store_path("tmp")
        curr_app_config["STORE_MAIN_DIR"] = cls.store_path("live")
        curr_app_config["STORE_TYPE"] = None  # Force StoreFactory to use STORE_IMPL
        curr_app_config["STORE_IMPL"] = "octopus.modules.store.store.StoreLocal"
        curr_app_config["LOGFILE"] = "/tmp/sword-out-tests.log"
        cls.storage_mgr = store.StoreLocal()

    @classmethod
    def setup_store(cls):
        def safe_makedirs(path):
            os.makedirs(path, exist_ok=True)

        # Set up store directories
        shutil.rmtree(cls.store, ignore_errors=True)
        safe_makedirs(current_app.config["STORE_TMP_DIR"])
        safe_makedirs(current_app.config["STORE_MAIN_DIR"])

    def setUp(self):
        super(SwordOutTestCase, self).setUp()
        self.setup_store()
