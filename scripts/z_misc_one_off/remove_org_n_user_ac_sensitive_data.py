#!/usr/bin/env python3
"""
Remove sensitive (identifying / secret) data from Org & User account records.  (E.g. For producing test data).
Script to do following:
  - Backup tables that will be modified:
        - account (Org-accounts)
        - acc_user (User accounts)
        - acc_notes_emails (Standard emails - contain email addresses)
        - acc_bulk_email (Bulk emails - contain email addresses).

  - Update Organisation accounts to anonymize the following data:
        - Contact email
        - Technical contact emails
        - For repo-accounts:
            - SWORD Credentials
  - Update User accounts to anonymize the following data:
        - User names
        - User emails
  - Update emails to anonymize email addresses
  - Update bulk emails to anonymize email addresses

AFTER running, if all is OK when tested, the backup tables can be deleted - Paste following into SQL editor & run:
    -- SQL to delete BACKED UP tables
    USE `jper`;
    DROP TABLES `acc_bulk_email_bak`, `acc_notes_emails_bak`, `account_bak`, `acc_user_bak`;


TO REVERT (reinstate original data from backed up tables) - Paste following into SQL editor & run:
    -- SQL to reinstate BACKED UP tables
    USE `jper`;

    -- Delete the modified tables
    DROP TABLES `acc_bulk_email`, `acc_notes_emails`, `account`, `acc_user`;

    -- Rename the backed up tables
    ALTER TABLE `acc_bulk_email_bak` RENAME TO  `acc_bulk_email` ;
    ALTER TABLE `acc_notes_emails_bak` RENAME TO  `acc_notes_emails` ;
    ALTER TABLE `account_bak` RENAME TO  `account` ;
    ALTER TABLE `acc_user_bak` RENAME TO  `acc_user` ;

"""
import re
import random
import string
from router.jper.app import app     # need to import app_decorator as other modules import it from here.
from octopus.core import initialise
from octopus.modules.mysql.utils import SQLUtils
from router.shared.models.account import AccOrg, AccUser, AccBulkEmail, AccNotesEmails

email_separators = re.compile(r'[;, \n\r]+')      # Email string will be split on these characters into a list

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

def random_string(s_len=None):
    if s_len is None:
        s_len = random.randrange(4, 8)
    return "".join(random.choices(string.ascii_lowercase, k=s_len))

def randomise_string(s, first_upper=None, not_empty=True):
    s_len = 0 if s is None else len(s)
    if s_len == 0:
        if not_empty:
            new_str = random_string()
        else:
            return ""
    else:
        new_str = random_string(s_len)
        if first_upper is None:
            first_upper = s[0].isupper()
    if first_upper:
        new_str = new_str[0].upper() + new_str[1:]
    return new_str

def randomise_email(email, firstname=None, lastname=None):
    # Split the email into username and domain
    if '@' not in email:
        return email
    local, domain = email.split('@', 1)
    if firstname is None:
        firstname = random_string()
    if lastname is None:
        lastname = random_string()
    return f"{firstname}.{lastname}@{domain}"

def randomise_emails_string(emails, split_str="; ", regex_split=False):
    email_list = email_separators.split(emails) if regex_split else emails.split(split_str)
    return split_str.join([randomise_email(email) for email in email_list])


class AdminDB:

    def __init__(self, env=None):
        DB_NAME = "jper"
        DB_ADMIN_USER = "admin"
        if env == "development":
            DB_NAME = "jper"
            DB_ADMIN_PWD = "1#er1*<Ss%WE&0QxA]C_mNS[C=0XERBI"
        elif env == "test":
            DB_ADMIN_PWD = "Test-Admin-Pwd"
        elif env == "staging":
            DB_ADMIN_PWD = "Stage-Admin-Pwd"
        elif env == "production":
            DB_ADMIN_PWD = "Prod-Admin-Pwd"
        else:
            abend(f"UNEXPECTED Environment: '{env}' - cannot set MySQL admin password")
        self.db_name = DB_NAME

        MYSQL_HOST = app.config.get("MYSQL_HOST") or "localhost"
        self.admin_db = SQLUtils(host=MYSQL_HOST, user=DB_ADMIN_USER, password=DB_ADMIN_PWD, db_name=DB_NAME)
        log_title(f"Running in '{env}' environment")

    def run_admin_query(self, sql, msg, commit=False, fetch=False):
        print(f"\n** Running query - {msg} **\n\tQuery: \"{sql}\"", flush=True)

        result = self.admin_db.run_query(sql, commit=commit, fetch=fetch)
        if not fetch:
            print("\tResult: ", result, "\n", flush=True)


with app.app_context():

    TEST = False
    initialise()
    ### ALter config to avoid outputting DEBUG log messages
    app.config["LOGLEVEL"] = "INFO"
    app.config["LOG_DEBUG"] = False

    env = app.config.get("OPERATING_ENV")
    admin_db = AdminDB(env)

    tables_to_backup = ["account", "acc_user", "acc_notes_emails", "acc_bulk_email"]
    try:
        if not TEST:
            for sql, msg in [
                (f"USE {admin_db.db_name};", f"Use '{admin_db.db_name}' database"),
            ]:
                admin_db.run_admin_query(sql, msg, commit=True)
            for table in tables_to_backup:
                backup_table = f"{table}_bak"
                for sql, msg in [
                    (f"CREATE TABLE {backup_table} LIKE {table};", f"Creating table '{backup_table}'"),
                    (f"INSERT INTO {backup_table} SELECT * FROM {table};", f"Populating '{backup_table}' from '{table}'")
                ]:
                    admin_db.run_admin_query(sql, msg, commit=True)

    except Exception as e:
        abend(f"ERROR while {msg} (executing query {sql}) - {repr(e)}")

    try:
        # Update ALL records to remove now redundant fields from AccOrg records (which have moved to AccUser records)
        # And also, change any "Developer" Org Acc to "Admin" Org Acc
        log_title("Modifying Org Account records except Admin Org")
        for acc in AccOrg.pull_all(for_update=True):
            # Skip Admin org
            if acc.raw_role == "A":
                continue

            acc.contact_email = randomise_email(acc.contact_email)
            acc.tech_contact_emails = [ randomise_email(email) for email in acc.tech_contact_emails ]

            if acc.raw_role == "R":  # Repo acc
                repo_data = acc.repository_data
                # Change SWORD account credentials (Username, Pwd, Collection)
                repo_data.add_sword_credentials(random_string(8), random_string(11), repo_data.sword_collection)

            if not TEST:
                acc.update()
            log_msg("INFO", f"Account updated (New contact email: {acc.contact_email})", org_id=acc.id, org_name=acc.org_name)

            # Modify all the organisation users
            for acc_user in AccUser.pull_user_acs(acc.id, for_update=True):
                users_name = acc_user.forename + " " + acc_user.surname
                acc_user.surname = randomise_string(acc_user.surname)
                acc_user.forename = randomise_string(acc_user.forename)
                acc_user.username = randomise_email(acc_user.username, firstname=acc_user.forename, lastname=acc_user.surname)
                # acc_user.org_role = randomise_string(acc_user.org_role)
                if not TEST:
                    acc_user.update()
                log_msg("INFO", f"User {users_name} (ID: {acc_user.id}) updated; New username: {acc_user.username}", org_id=acc.id, org_name=acc.org_name)

        log_title("Modifying Email records")
        AccNotesEmails.__pull_cursor_dict__["all"] = ("", None, None)
        for note_email in AccNotesEmails.pull_all(for_update=True):
            note_email_dict = note_email.data
            if not note_email_dict["type"] in ("E", "B"):       #NOT  Email or Bulk email
                continue
            note_email_dict["to_addr"] = randomise_emails_string(note_email_dict.get("to_addr", ""))
            note_email_dict["cc_addr"] = randomise_emails_string(note_email_dict.get("cc_addr", ""))
            print("ID:", note_email_dict["id"] ,"\nTo:", note_email_dict["to_addr"], "\nCC:", note_email_dict["cc_addr"], "\n")
            if not TEST:
                note_email.update()

        log_title("Modifying Bulk Email records")
        AccBulkEmail.__pull_cursor_dict__["all"] = ("", None, None)
        for bulk_email in AccBulkEmail.pull_all(for_update=True):
            bulk_email_dict = bulk_email.data
            bulk_email_dict["cc_addr"] = randomise_emails_string(bulk_email_dict.get("cc_addr", ""), split_str="; ", regex_split=True)
            bulk_email_dict["bcc_to_addr"] = randomise_emails_string(bulk_email_dict.get("bcc_to_addr", ""), split_str=";")
            bulk_email_dict["bcc_cc_addr"] = randomise_emails_string(bulk_email_dict.get("bcc_cc_addr", ""), split_str=";")
            print("ID:", bulk_email_dict["id"], "\nCC:", bulk_email_dict["cc_addr"], "\nTo-bcc:", bulk_email_dict["bcc_to_addr"],"\nCC-bcc:", bulk_email_dict["bcc_cc_addr"],"\n")
            if not TEST:
                bulk_email.update()

        if not TEST:
            AccOrg.commit()
            AccUser.commit()
            AccNotesEmails.commit()
            AccBulkEmail.commit()
    except Exception as e:
        abend(f"ERROR while processing - {repr(e)}")

    log_title(f"ALL DONE")
