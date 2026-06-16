#!/usr/bin/env python3
"""
Script to check which Org Accounts have NO users.
"""

from router.jper.app import app     # need to import app_decorator as other modules import it from here.
from octopus.core import initialise
from router.shared.models.account import AccOrg, AccUser


def log_title(msg):
    print(f"\n***** {msg} *****\n")


def format_msg(msg, row_num=None, org_id=None, org_name=""):
    return (f"Row {row_num: <3} - " if row_num else "") + (f"Org-ID {org_id: <3} <{org_name}> - " if org_id else "") + msg


def log_msg(level, msg, row_num=None, org_id=None, org_name=""):
    print(f"{level + ':': <7}{format_msg(msg, row_num, org_id, org_name)}")


# Abnormal End
def abend(msg):
    log_title(f"ABEND - {msg}")
    exit(1)


with app.app_context():
    all_ok = True
    initialise()
    ### ALter config to avoid outputting DEBUG log messages
    app.config["LOGLEVEL"] = "INFO"
    app.config["LOG_DEBUG"] = False

    log_title(f"Checking for Org accounts without any Users")
    missing_count = 0
    # Check if any accounts without users
    for acc in AccOrg.get_all_undeleted_accounts_of_type():
        users = AccUser.pull_user_acs(acc.id)
        num_users = len(users)
        if num_users == 0:
            log_msg("INFO", f"NO user", org_id=acc.id, org_name=acc.org_name)
            missing_count += 1
        # else:
        #     log_msg("OK", f"{num_users} user(s)", org_id=acc.id, org_name=acc.org_name)
    if missing_count:
        log_msg("*****", f"{missing_count} Account (OrgAcc) record(s) with no users - see above.")
        all_ok = False

    log_title(f"ALL DONE - {'OK' if all_ok else f'{missing_count} USERS MISSING'}")
