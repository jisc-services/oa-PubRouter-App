#!/usr/bin/env python3
"""
Script to do following:
  - Verify user spreadsheet(s)
"""
import csv
from router.jper.app import app     # need to import app_decorator as other modules import it from here.
from octopus.core import initialise
from router.shared.models.account import AccOrg

USER_CSV_FILE = "./user_csv_files/{}_users.csv"


def log_title(msg):
    print(f"\n***** {msg} *****\n")


def format_msg(msg, row_num=None, org_id=None, org_name=""):
    return (f"Row {row_num: <3} - " if row_num else "") + (f"Org-ID {org_id: <3} <{org_name}> - " if org_id else "") + msg


def log_msg(level, msg, row_num=None, org_id=None, org_name=""):
    print(f"{level + ':': <6} {format_msg(msg, row_num, org_id, org_name)}")


# Abnormal End
def abend(msg):
    log_title(f"ABEND - {msg}")
    exit(1)


def verify_user_csv(filepath):
    """
    We expect CSV file to have columns in this order:
    - Type (R or P)
    - Org name
    - Org ID
    - Acc status
    - User email address
    - User type character
    - Last name
    - First name
    - Org role
    - Comments

    @param filepath:
    @return:
    """
    log_title(f"Verifying user spreadsheet: '{filepath}'")

    orgs_found = {}
    orgs_no_email = {}
    ok = True
    row_num = 0
    with open(filepath, newline='') as f:
        reader = csv.reader(f)
        _ = next(reader)  # gets the first line containing column headings
        for row in reader:
            row_num += 1
            rec_type, org_name, org_id, acc_status, email, user_type, surname, firstname, role, comment = row[:10]

            rec_type = rec_type.strip()
            org_name = org_name.strip()
            org_id = org_id.strip()
            email = email.strip().lower()
            user_type = user_type.strip().upper() if user_type else "A"     # Default to admin
            surname = surname.strip()
            firstname = firstname.strip()
            role = role.strip()
            comment = comment.strip()

            if not org_id:
                log_msg("INFO", "Missing Org-ID", row_num=row_num)
                continue

            org_acc = AccOrg.pull(org_id)
            if not org_acc:
                log_msg("ERROR", f"Account NOT FOUND", row_num, org_id, org_name)
                ok = False
                continue

            if org_acc.deleted_date:
                log_msg("INFO", f"Account DELETED - User will NOT be created", row_num, org_id, org_name)

            if orgs_found.get(org_id):
                log_msg("INFO", f"Multiple users specified", row_num, org_id, org_name)
            else:
                orgs_found[org_id] = org_name

            if rec_type != org_acc.raw_role:
                log_msg("ERROR", f"Record type mismatch (expected: '{org_acc.raw_role}', found: '{rec_type}')", row_num, org_id, org_name)
                ok = False

            if org_name.lower() != org_acc.org_name.lower():
                log_msg("ERROR", f"Org name mismatch (expected: '{org_acc.org_name}')", row_num, org_id, org_name)
                ok = False

            if email:
                _, _, domain = email.partition("@")
                if not domain:
                    log_msg("ERROR", f"Bad email '{email}'", row_num, org_id, org_name)
                    ok = False

                org_domain = None
                if org_acc.contact_email:
                    _, _, org_domain = org_acc.contact_email.partition("@")
                if org_domain:
                    org_domain = org_domain.lower()
                    if domain != org_domain:
                        if org_domain.endswith(domain):
                            log_msg("INFO", f"Email domain '{domain}' different from current contact '{org_domain}'", row_num, org_id, org_name)

                        else:
                            log_msg("ERROR", f"Email domain mismatch in '{email}' (expected: '{org_domain}', found: '{domain}')", row_num, org_id, org_name)
                            ok = False
                else:
                    log_msg("INFO", f"Current contact '{org_acc.contact_email}' is not an email", row_num, org_id, org_name)

                if user_type not in ["A", "S", "R", "J", "D"]:
                    log_msg("ERROR", f"Unexpected user-type '{user_type}'", row_num, org_id, org_name)
                    ok = False

                if not surname:
                    log_msg("ERROR", "Missing surname", row_num, org_id, org_name)
                    ok = False

                if not firstname:
                    log_msg("ERROR", "Missing first-name", row_num, org_id, org_name)
                    ok = False

                if not role:
                    log_msg("INFO", "Missing Org role", row_num, org_id, org_name)
            else:
                msg = format_msg("", row_num, org_id, org_name)
                orgs_no_email[org_id] = msg
                log_msg("WARN", f"{msg}Missing EMAIL in CSV (Org contact: {org_acc.contact_email})")

            if comment:
                log_msg("INFO", f"COMMENT: {comment}", row_num, org_id, org_name)

    if not ok:
        log_title(f"PROBLEM with CSV file '{filepath}'")
    return ok, orgs_found, orgs_no_email


with app.app_context():

    initialise()
    ### ALter config to avoid outputting DEBUG log messages
    app.config["LOGLEVEL"] = "INFO"
    app.config["LOG_DEBUG"] = False

    ### XXXXXXXXXXXXXXXXXXXX
    # app.config["OPERATING_ENV"] = "staging"
    # app.config["MYSQL_HOST"] = "dr-oa-stage-pubrouter.cewhgxkzt0vu.eu-west-1.rds.amazonaws.com"  # RDS Pre-Prod (staging) instance
    # app.config["MYSQL_PWD"] = "k=K5MGthGFXUw=^BB&2G$fww"  # Password for MYSQL_USER "jper_user"

    env = app.config.get("OPERATING_ENV")
    csv_file = USER_CSV_FILE.format(env)

    ok, orgs_found, orgs_no_email = verify_user_csv(csv_file)

    for acc in AccOrg.get_all_undeleted_accounts_of_type():
        if not orgs_found.get(str(acc.id)):
            log_msg("ERROR", f"No entry in spreadsheet for {acc.role} account - Contact: {acc.contact_email}", org_id=acc.id, org_name=acc.org_name)
            ok = False

    print(f"\n***** ALL DONE - {'OK' if ok else 'ERRORS'} *****\n")
