#!/usr/bin/env python
"""
Script to CREATE A DATABASE (named 'jper') plus 'jper_user' database user.

In non-production environments a 'test_admin' database user is also created.


Also, create Router admin account.

Usage:
    create_database db-root-user db-root-pwd

"""
import uuid
import sys
from octopus.core import initialise
from octopus.modules.mysql import utils
from router.shared.mysql_db_ddl import JPER_TABLES, JPER_REPORTS_TABLES
from router.shared.create_admin_acc import create_admin_user
from router.jper.app import app

if __name__ == "__main__":

    with app.app_context():
        allowed_envs = ('production','development','staging', 'test')
        initialise()

        operating_env = app.config.get("OPERATING_ENV")
        if operating_env not in allowed_envs:
            print(f"\n\nExiting - script will ONLY RUN in one of these environments: {allowed_envs}.\n\n")
            exit(0)

        try:
            root_user = sys.argv[1]
        except IndexError:
            root_user = "root"

        try:
            root_pwd = sys.argv[2]
        except IndexError:
            root_pwd = "admin"

        db_name = app.config["MYSQL_DB"]

        user_priv = ["SELECT", "INSERT", "UPDATE", "DELETE", "DROP", "EXECUTE", "LOCK TABLES", "CREATE TEMPORARY TABLES"]
        db = utils.SQLUtils(host=app.config["MYSQL_HOST"], user=root_user, password=root_pwd)

        # Create database if it doesn't already exist
        try:
            db.use_db(db_name)  # Will raise Exception if database does NOT exist
        except Exception as e:
            db.create_database(db_name)
            db.use_db(db_name)
            print(f"\nDatabase '{db_name}' created.\n")
        else:
            print(f"\nDatabase '{db_name}' already exists... quitting.\n")
            exit(0)

        # Create std JPER user
        user_name = app.config["MYSQL_USER"]
        user_pwd = app.config["MYSQL_PWD"]
        db.create_user(user_name, app.config["MYSQL_HOST"], user_pwd, user_priv, f"{db_name}.*")
        print(f"\n\nUser '{user_name}' created with Password '{user_pwd}' with Privileges {user_priv} on Database '{db_name}.*'.")

        # Create all database tables
        db.create_tables(JPER_TABLES)
        db.create_tables(JPER_REPORTS_TABLES)
        print(f"\nTables created for database: '{db_name}'.")

        # Except for production environment, create test_admin user
        if operating_env != "production":
            test_admin_name = "test_admin"
            test_admin_pwd = app.config["TEST_DB_ADMIN_PWD"]
            test_admin_priv = ["CREATE", "CREATE USER", "DELETE", "DROP", "EXECUTE", "GRANT OPTION", "INDEX", "INSERT",
                               "SELECT", "UPDATE"]
            db.create_user(test_admin_name, app.config["MYSQL_HOST"], test_admin_pwd, test_admin_priv, "*.*")
            print(
                f"\n\nDB Test Admin user '{test_admin_name}' created with Password '{test_admin_pwd}' with Privileges {test_admin_priv} on Database '*.*'.")

        # Create Router application admin user
        api_key = str(uuid.uuid4())
        ac_created, acc = create_admin_user(api_key)
        print("\n\n=== {} - {}. ===\n".format(
            f"New application Admin account CREATED with api_key: {api_key}" if ac_created else "Admin account already exists",
            f"account ID: {acc.id}, UUID: {acc.uuid}")
        )
