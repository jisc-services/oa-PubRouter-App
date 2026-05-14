#!/usr/bin/env python
"""
Script to CREATE A DEVELOPMENT ENVIRONMENT DATABASE (named 'jper') plus 'jper_user' database user.

Also, create Router admin account.

Usage:
    create_dev_db  db-root-pwd

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
        initialise()

        if app.config.get("OPERATING_ENV") != "development":
            print("\n\nExiting - script will ONLY RUN in development environment\n\n")
            exit(0)
        try:
            root_pwd = sys.argv[1]
        except KeyError:
            root_pwd = "admin"

        db_name = app.config["MYSQL_DB"]

        user_priv = ["SELECT", "INSERT", "UPDATE", "DELETE", "DROP", "EXECUTE", "LOCK TABLES", "CREATE TEMPORARY TABLES"]
        db = utils.SQLUtils(host=app.config["MYSQL_HOST"], user="root", password=root_pwd)

        # Create database
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
        print(f"\nDatabase tables created.")

        # Create admin user
        api_key = str(uuid.uuid4())
        ac_created, acc = create_admin_user(api_key)
        print("\n=== {} - {}. ===\n".format(
            f"New Admin account CREATED with api_key: {api_key}" if ac_created else "Admin account already exists",
            f"account ID: {acc.id}, UUID: {acc.uuid}")
        )