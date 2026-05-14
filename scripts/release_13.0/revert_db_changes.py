#!/usr/bin/env python3
#
# Script REVERT effect of running migrate_match_params.py
#

from router.jper.app import app     # need to import app_decorator as other modules import it from here.
from octopus.core import initialise
from octopus.modules.mysql.utils import SQLUtils


def log_title(msg):
    print(f"\n***** {msg} *****\n")


# Abnormal End
def abend(msg):
    log_title(f"ABEND - {msg}")
    exit(1)


class AdminDB:

    def __init__(self, env=None):
        DB_NAME = "jper"
        DB_ADMIN_USER = "admin"
        if env == "development":
            DB_ADMIN_PWD = "1#er1*<Ss%WE&0QxA]C_mNS[C=0XERBI"
        elif env == "test":
            DB_ADMIN_PWD = "HuCfbmgVCBLURSMxOrDf"
        elif env == "staging":
            DB_ADMIN_PWD = "Nn6caDHHp1vKfEDmRDPI"
        elif env == "production":
            DB_ADMIN_PWD = "9Y5yfjSEEHvgtyVjwwRL"
        else:
            abend(f"UNEXPECTED Environment: '{env}' - cannot set MySQL admin password")

        MYSQL_HOST = app.config.get("MYSQL_HOST") or "localhost"
        self.admin_db = SQLUtils(host=MYSQL_HOST, user=DB_ADMIN_USER, password=DB_ADMIN_PWD, db_name=DB_NAME)
        log_title(f"Running in '{env}' environment")

    def run_admin_query(self, sql, msg, commit=False, fetch=False):
        print(f"\n** Running query - {msg} **\n\tQuery: \"{sql}\"", flush=True)

        result = self.admin_db.run_query(sql, commit=commit, fetch=fetch)
        if not fetch:
            print("\tResult: ", result, "\n", flush=True)


with app.app_context():

    initialise()
    ### ALter config to avoid outputting DEBUG log messages
    app.config["LOGLEVEL"] = "INFO"
    app.config["LOG_DEBUG"] = False

    env = app.config.get("OPERATING_ENV")
    admin_db = AdminDB(env)

    backup_acc_tbl = "account_rel12_bak"
    log_title(f"Reverting changes using '{backup_acc_tbl}' backup")

    try:
        for sql, msg in [
            ("USE jper;", "Use 'jper' database"),
            ("DROP TABLE acc_user;", "Dropping 'acc_user' table"),
            ("DROP TABLE `account`;", "Dropping 'account' table"),
            (f"RENAME TABLE {backup_acc_tbl} TO `account`;", f"Renaming  '{backup_acc_tbl}' --> 'account' table")
        ]:
            admin_db.run_admin_query(sql, msg, commit=True)
    except Exception as e:
        abend(f"ERROR while {msg} (executing query {sql}) - {repr(e)}")

log_title("ALL DONE")