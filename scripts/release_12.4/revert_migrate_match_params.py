#!/usr/bin/env python3
#
# Script REVERT effect of running migrate_match_params.py
#

from router.jper.app import app     # need to import app_decorator as other modules import it from here.
from octopus.core import initialise
from octopus.modules.mysql.utils import SQLUtils


def abend(msg):
    print(f"\n***** ABEND - {msg} *****\n")
    exit(1)


class AdminDB:

    def __init__(self):
        DB_NAME = "jper"
        DB_ADMIN_USER = "admin"
        env = app.config.get("OPERATING_ENV")
        if env == "development":
            DB_ADMIN_PWD = "1#er1*<Ss%WE&0QxA]C_mNS[C=0XERBI"
        elif env == "test":
            DB_ADMIN_PWD = "HuCfbmgVCBLURSMxOrDf"
        elif env == "staging":
            DB_ADMIN_PWD = "Nn6caDHHp1vKfEDmRDPI"
        elif env == "production":
            DB_ADMIN_PWD = "9Y5yfjSEEHvgtyVjwwRL"
        else:
            abend("UNEXPECTED Environment: '{env}' - cannot set MySQL admin password")

        MYSQL_HOST = app.config.get("MYSQL_HOST") or "localhost"
        self.admin_db = SQLUtils(host=MYSQL_HOST, user=DB_ADMIN_USER, password=DB_ADMIN_PWD, db_name=DB_NAME)

    def run_admin_query(self, sql, msg, commit=False, fetch=False):
        print(f"\n** Running query - {msg} **\n\tQuery: \"{sql}\"", flush=True)

        result = self.admin_db.run_query(sql, commit=commit, fetch=fetch)
        if not fetch:
            print("\tResult: ", result, "\n", flush=True)


with app.app_context():

    initialise()

    admin_db = AdminDB()

    print("\n***** REVERTING to original state ****\n")
    for sql, msg in [("TRUNCATE TABLE acc_repo_match_params;", "Truncating table 'acc_repo_match_params'"),
                     ("DROP TABLE `account`;", "Dropping 'account' table"),
                     ("RENAME TABLE account_original TO `account`;", "Renaming  'account_original' --> 'account' table"),
                     ]:
        admin_db.run_admin_query(sql, msg, commit=True)

    print("\n***** ALL DONE *****\n")
