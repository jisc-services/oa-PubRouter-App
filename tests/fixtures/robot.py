"""
Robot related test functions

**** IMPORTANT **** These tests are likely to FAIL as use of the Robot test suite was discontinued several years ago.

These functions are used inside the robot testing framework.

**IMPORTANT** - Inside the robot test framework these functions are called using robot nomenclature which drops the
underscores, as shown here by example:
    --Function--                | --How it is called from within framework--
    server_setup()              | Server Setup
    delete_account_test_data()  | Delete Account Test Data

This also includes a version of JPER that is prefixed to /robot.
(So routes are like /robot/accounts/admin, /robot/harvester/webservice, etc.)

The testing version of JPER can be started by `python3 -m tests.fixtures.robot`.
"""
import os
from router.jper.app import app_decorator, app

TEST_DB_ADMIN_USER = "test_admin"   # Pre-existing DB Admin user with permissions to create database & tables
TEST_DB_ADMIN_PWD = "_test#db#admin%1234%pwd_"

ROBOT_DB_NAME = "robot"     # Name of db schema to be used for robot tests

## Override database config ##
# app.config["MYSQL_HOST"] = "localhost"
app.config["MYSQL_USER"] = "robot_user"     # User to be created with basic db table access permissions (INSERT, UPDATE etc.etc.)
app.config["MYSQL_PWD"] = "robotPwd1"
app.config["MYSQL_DB"] = ROBOT_DB_NAME

app.config["PORT"] = 5000
# Disable creation of FTP accounts on UNIX so we don't add a bunch of bad accounts to the server
app.config["UNIX_FTP_ACCOUNT_ENABLE"] = False

from logging import config
from octopus.core import initialise
from octopus.modules.mysql import utils
from router.shared.mysql_db_ddl import JPER_TABLES
from tests.jper_tests.fixtures.models import IdentifierFactory

print("\n*** CONFIG:", app.config, "\n***end config***\n")
_db_conn = utils.SQLUtils(host=app.config["MYSQL_HOST"], user=TEST_DB_ADMIN_USER, password=TEST_DB_ADMIN_PWD)

@app_decorator
def clear_down_data_tables():
    tables_except_account = list(JPER_TABLES.keys())
    tables_except_account.remove("account")
    _db_conn.truncate_tables(tables_except_account)   # Empty specified tables
    # Delete all account records except for the first which is Admin account
    _db_conn.run_query("DELETE FROM account WHERE api_key != 'admin';", commit=True)
    print("-- Truncated tables")


@app_decorator
def server_setup():
    """
    Called from within robot as: 'Server Setup'.

    Creates database for use by Robot.
    :return: nothing
    """
    _db_conn.drop_database(ROBOT_DB_NAME)     # Drop database (if it exists)
    _db_conn.create_database(ROBOT_DB_NAME)   # Create (empty i.e. no data tables) database schema

    # Create db user that will be used for tests
    all_tables_in_test_db = ROBOT_DB_NAME + ".*"
    # db user privileges (DROP is needed by truncate_table function)
    _db_conn.create_user(app.config["MYSQL_USER"],
                         "%",
                         app.config["MYSQL_PWD"],
                         ["SELECT", "INSERT", "UPDATE", "DELETE", "DROP"],
                         all_tables_in_test_db
                         )
    # Create db tables
    _db_conn.create_tables(JPER_TABLES)
    print("\n*** Before initialise() MYSQL CONFIG Host: '{}'  D/b: '{}'  User: '{}' ***\n".format(
        app.config["MYSQL_HOST"], app.config["MYSQL_DB"], app.config["MYSQL_USER"]))
    initialise()    # This will create an admin user in database


@app_decorator
def server_teardown():
    """
    Close database - leave contents there, as may be useful to look at after test has ended (they
    will be deleted by server_setup() next time robot tests are run).
    """
    _db_conn.close()


@app_decorator
def reset_harvester_data():
    _db_conn.truncate_tables(["h_webservice", "h_errors", "h_history"])


@app_decorator
def delete_account_test_data():
    """
    Deletes all Account test data in the the robot index
    """
    # Delete all account records except for Admin account
    _db_conn.run_query("DELETE FROM account WHERE api_key != 'admin';", commit=True)
    print("Account records deleted")

@app_decorator
def delete_identifier_test_data():
    """
    Deletes all identifier data in the the robot index
    """
    _db_conn.truncate_tables("org_identifiers")


@app_decorator
def create_test_identifiers():
    """
    Make two simple identifiers to test the fuzzy search
    """
    IdentifierFactory.make_jisc("University of Nowhere")
    IdentifierFactory.make_core("University of Nowhere")


def join_paths_together(path, *args):
    """
    This allows the use of the keyword "Join Paths Together" inside robot tests.

    :param path: Initial path segment
    :param args: List of paths to join

    :return: os.path.join of the arguments
    """
    # In case part of path is an integer, convert all to string
    return os.path.join(path, *[str(a) for a in args])


def default_epmc_url():
    """
    This allows the use of the keyword "Default EPMC Url" inside robot tests.

    :return: EPMC url
    """
    return app.config["WEBSERVICES_DATA_EPMC"]["url"]

if __name__ == '__main__':
    # __main__ runs JPER web application on localhost:5000 for use by Robot tests

    # Import jper.web_main here so we don't have any issues with importing octopus es too early

    server_setup()
    app.config["SERVER_NAME"] = "localhost:5000"
    app.run(host='0.0.0.0', port=app.config["PORT"], threaded=True)
else:
    # Execution occurs in the context of running robot tests

    # Disable most loggers so when we run robot tests we don't get log spam
    config.dictConfig({
        'version': 1,
        'disable_existing_loggers': True
    })
