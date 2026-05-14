
from flask import current_app
from octopus.modules.mysql.dao import DAO, DAOGlobals
from octopus.modules.testing.testcase import TestMySQL
from octopus.core import initialise
from router.shared.mysql_db_ddl import JPER_TABLES
from router.shared.create_admin_acc import create_admin_user


class JPERMySQLTestCase(TestMySQL):
    TEST_USER = "tester"         # User to be created with basic db table access permissions (INSERT, UPDATE etc.etc.)
    TEST_PWD = "TestPwd1"
    TEST_PRIV = ["SELECT", "INSERT", "UPDATE", "DELETE", "DROP"]  # db user privileges - DROP needed by truncate_table()

    admin_acc = None

    tables_for_testing = NotImplemented

    @classmethod
    def setUpClass(cls):
        """
        Create JPER test database tables.  NB. The database is created by TestMySQL.setUpClass().
        """
        super(JPERMySQLTestCase, cls).setUpClass()


        # Set up Dict of tables required for testing
        if cls.tables_for_testing is NotImplemented:
            raise NotImplementedError("List `tables_for_testing` needs to be initiated in setUpClass() with list of table names")

        cls.need_admin_user = "acc_user" in cls.tables_for_testing
        cls.tables_except_account_n_accuser = cls.tables_for_testing.copy()
        if cls.need_admin_user:
            cls.tables_except_account_n_accuser.remove("account")
            cls.tables_except_account_n_accuser.remove("acc_user")

        # Create tables needed for testing
        if cls.tables_for_testing:
            # Pass dictionary containing DDL for just the tables needed for testing
            cls.db.create_tables({k: JPER_TABLES[k] for k in cls.tables_for_testing})

        # Create test user
        all_tables_in_test_db = cls.test_db_name + ".*"
        cls.db.create_user(cls.TEST_USER, "%", cls.TEST_PWD, cls.TEST_PRIV, all_tables_in_test_db)

        curr_app_config = current_app.config  # Do this to avoid repeatedly calling current_app local-proxy

        # curr_app_config["MYSQL_HOST"] - rely on original setting
        curr_app_config["MYSQL_USER"] = cls.TEST_USER
        curr_app_config["MYSQL_PWD"] = cls.TEST_PWD
        curr_app_config["MYSQL_DB"] = cls.test_db_name
        curr_app_config["MYSQL_TIMEZONE"] = "+00:00"     # causes MySQL to return stored timestamps as UTC values
        curr_app_config["MYSQL_POOL_SIZE"] = None        # Not using connection pool
        curr_app_config["MYSQLX_MULTI_POOL"] = False     # Single pool - needs larger pool size (if pool used)
        curr_app_config['MAIL_MOCKED'] = True    # "print"  (Replace True by "print" to cause emails to be printed)

        initialise()
        if cls.need_admin_user:
            _, cls.admin_user_acc = create_admin_user()     # Create default Router admin user account

    def setUp(self):
        super(JPERMySQLTestCase, self).setUp()
        if self.tables_except_account_n_accuser:
            self.db.truncate_tables(self.tables_except_account_n_accuser)
        if self.need_admin_user:
            # Delete all account & associated acc_user records except for the first which is Admin account
            # Use LEFT JOIN here because test `account` records may be created without corresponding `acc_user` entries
            self.db.run_query(f"DELETE account, acc_user FROM account LEFT JOIN acc_user ON account.id = acc_user.acc_id WHERE account.id != {self.admin_user_acc.org_id};", commit=True)
        print("-- Truncated tables")

    def tearDown(self):
        print("\n-- DIAGNOSTICS BEFORE closing all connections",  DAO.diagnostics_str(), "\n")
        DAO.close_all_connections()
        DAOGlobals.clear_errors()

        super(JPERMySQLTestCase, self).tearDown()

