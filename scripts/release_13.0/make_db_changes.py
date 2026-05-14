#!/usr/bin/env python3
"""
Script to do following:
  - backup of account table
  - Create acc_user table
  - Add a user record in acc_user table for each account in account table
  - Modify account table to remove username column
  - Update account records to remove the following fields:
      username
      password
      reset_token
      last_login_attempt
      failed_login_count
  - Add user records to acc_user table
"""

import csv
from router.jper.app import app     # need to import app_decorator as other modules import it from here.
from octopus.core import initialise
from octopus.modules.mysql.utils import SQLUtils
from router.shared.models.account import AccOrg, AccUser
from router.shared.mysql_db_ddl import JPER_TABLES

USER_CSV_FILE = "./user_csv_files/{}_users.csv"


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


def create_user_ac(org_id, org_name, email, firstname, surname, role, user_type, org_acc_raw_role, row_num=None):
    ok = True
    try:
        # If parent org is Admin or Developer organisation
        if org_acc_raw_role in ['A', 'D']:
            # Change 'A' admin code to 'J' (Jisc admin) or 'D' (Developer)
            if user_type == 'A':
                user_type = 'J' if org_acc_raw_role == 'A' else 'D'
        # Create user from CSV file
        user_acc = AccUser({
            "id": None,
            "created": None,
            "last_success": None,
            "last_failed": None,
            "failed_login_count": 0,
            "direct_login": user_type == 'D',   # ALlow Developers to directly log in
            "uuid": None,
            "acc_id": int(org_id),
            "username": email,
            "surname": surname,
            "forename": firstname,
            "org_role": role or None,
            "role_code": user_type,
            "user_email": ""
        })
        user_acc.set_password("66_Funkey%Chicken_55" if user_type == "D" else user_acc.create_uuid())
        password_reset_token = user_acc.create_reset_token()
        user_acc.insert()
        log_msg("OK",
                f"CREATED User record for <{firstname} {surname}> - Username: {email}, ID: {user_acc.id}, UUID: {user_acc.uuid}, Role: {user_acc.role_short_desc}, Pwd-reset-token: {password_reset_token}",
                row_num, org_id, org_name)
    except Exception as e:
        log_msg("ERROR", f"Exception inserting record for <{firstname} {surname}> - {repr(e)}", row_num, org_id,
                org_name)
        ok = False

    return ok

def create_user_recs(filepath):
    """
    Create new user records from contents of CSV file.

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

    :param filepath: Path to CSV file
    :return:
    """
    log_title(f"Creating users from user spreadsheet: '{filepath}'")

    orgs_found = {}
    users_not_created = []
    all_ok = True
    row_num = 0
    with open(filepath, newline='') as f:
        reader = csv.reader(f)
        _ = next(reader)  # gets the first line containing column headings
        for row in reader:
            ok = True
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
                log_msg("ERROR", "Missing Org-ID", row_num=row_num)
                ok = False
                continue

            org_acc = AccOrg.pull(org_id)
            if not org_acc:
                log_msg("ERROR", f"Account NOT FOUND", row_num, org_id, org_name)
                ok = False
                continue

            if org_acc.deleted_date:
                log_msg("INFO", f"Account DELETED - SKIPPING user creation", row_num, org_id, org_name)
                continue

            if orgs_found.get(org_id):
                log_msg("INFO", f"Multiple users for '{orgs_found.get(org_id)}'", row_num, org_id, org_name)
            else:
                orgs_found[org_id] = org_name

            org_acc_raw_role = org_acc.raw_role
            if rec_type != org_acc_raw_role:
                log_msg("ERROR", f"Record type mismatch (expected: '{org_acc_raw_role}', found: '{rec_type}')", row_num, org_id, org_name)
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
                            log_msg("WARN", f"Email domain mismatch in '{email}' (expected: '{org_domain}', found: '{domain}')", row_num, org_id, org_name)
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
                log_msg("WARN", f"Missing data", row_num, org_id, org_name)

            if comment:
                log_msg("INFO", f"COMMENT: {comment}", row_num, org_id, org_name)

            if email and ok:
                ok = create_user_ac(org_id, org_name, email, firstname, surname, role, user_type, org_acc_raw_role, row_num)
                if ok:
                    continue

            # If we get this far then there was an error
            msg = format_msg(f"SKIPPED user creation for <{firstname} {surname}>", row_num, org_id, org_name)
            users_not_created.append((row_num, org_id, msg))
            all_ok = False
            log_msg("FAIL", msg)
    if not all_ok:
        log_title(f"Summary of user records NOT CREATED...")
        for _, _, msg in users_not_created:
            log_msg("FAIL", msg)

    return all_ok, orgs_found, users_not_created


with app.app_context():

    initialise()
    ### ALter config to avoid outputting DEBUG log messages
    app.config["LOGLEVEL"] = "INFO"
    app.config["LOG_DEBUG"] = False

    env = app.config.get("OPERATING_ENV")
    csv_file = USER_CSV_FILE.format(env)
    admin_db = AdminDB(env)

    backup_acc_tbl = "account_rel12_bak"
    log_title(f"Creating '{backup_acc_tbl}' backup from 'account' table; creating 'acc_user' table; dropping 'username' column from 'account' table")

    try:
        for sql, msg in [
            ("USE jper;", "Use 'jper' database"),
            (f"CREATE TABLE {backup_acc_tbl} LIKE account;", f"Creating table '{backup_acc_tbl}'"),
            (f"INSERT INTO {backup_acc_tbl} SELECT * FROM account;", f"Populating '{backup_acc_tbl}'"),
            (JPER_TABLES["acc_user"], "Creating table 'acc_user'"),
            ("ALTER TABLE `account` DROP COLUMN `username`, DROP INDEX `user`;", "Dropping 'username' column from 'account' table")
        ]:
            admin_db.run_admin_query(sql, msg, commit=True)
    except Exception as e:
        abend(f"ERROR while {msg} (executing query {sql}) - {repr(e)}")

    ## !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!  FOR TESTING
    # AccOrg.__table__ = "account_test"

    try:
        # Update ALL records to remove now redundant fields from AccOrg records (which have moved to AccUser records)
        # And also, change any "Developer" Org Acc to "Admin" Org Acc
        log_title("Removing 'password', 'reset_token', 'last_login_attempt', 'failed_login_count' from 'account' records")
        for acc in AccOrg.pull_all(for_update=True):
            data_dict = acc.data
            deleted_fields = []
            for field in ['password', 'reset_token', 'last_login_attempt', 'failed_login_count']:
                try:
                    del data_dict[field]
                    deleted_fields.append(field)
                except KeyError:
                    pass
            if deleted_fields:
                acc.update()
            log_msg("INFO", f"Deleted fields: {deleted_fields}", org_id=acc.id, org_name=acc.org_name)

        AccOrg.commit()
    except Exception as e:
        abend(f"ERROR while removing redundant fields from existing 'account' records - {repr(e)}")

    all_ok, orgs_found, users_not_created = create_user_recs(csv_file)

    log_title(f"Checking Org account Users")
    missing_count = 0
    # Check if any accounts without users; ALSO change any Development Org-Acc to an Admin Org-ACC
    for acc in AccOrg.get_all_undeleted_accounts_of_type(for_update=True):
        # Change Dev org-acc to Admin org-acc
        if acc.raw_role == "D":
            acc.raw_role = "A"
            acc.update()
            log_msg("INFO", f"Changed Org-Acc type from Developer to Admin", org_id=acc.id, org_name=acc.org_name)
        users = AccUser.pull_user_acs(acc.id)
        num_users = len(users)
        if num_users == 0:
            email = acc.contact_email
            if email:
                log_msg("INFO", f"Missing user - Creating from Contact-email ({email})", org_id=acc.id, org_name=acc.org_name)
                ok = create_user_ac(acc.id, acc.org_name, email,"Shared", "User", "Contact", "S", acc.raw_role)
                if not ok:
                    log_msg("ERROR", f"FAILED to create user for Contact-email ({email})", org_id=acc.id, org_name=acc.org_name)
            else:
                log_msg("ERROR", f"NO USER - Org-account has NO Contact-email so cannot create a user", org_id=acc.id, org_name=acc.org_name)
            missing_count += 1

        else:
            log_msg("ok", f"{num_users} user(s)", org_id=acc.id, org_name=acc.org_name)
    if missing_count:
        log_msg("*****", f"Attempted to create {missing_count} Standard user(s) using Org Contact email - see above.")
        all_ok = False

    log_title(f"ALL DONE - {'OK' if all_ok else 'ERRORS'}")
