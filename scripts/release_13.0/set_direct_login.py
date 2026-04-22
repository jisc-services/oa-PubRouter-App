#!/usr/bin/env python3
"""
Script to set direct-login for all user accounts
"""

from octopus.core import initialise
from octopus.lib.mail import MailMsg, MailAccount
from router.jper.web_main import app     # need to import app_decorator as other modules import it from here.
from router.shared.models.account import AccUser


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

EMAIL_KNOWN = "Dear {} {}<br><br>"
EMAIL_UNKNOWN = "Dear User<br><br>"

TWO_STAGE = "It has come to our attention that two factor authentication isn't working for many users because their organisation's email security policy modifies links embedded in emails. Accordingly your account has been set to <i>direct login</i> which means that you will be logged in when you enter valid credentials (no login-link will be emailed)."
ADMIN_EXTRA = "<br><br>Note that any new user accounts that you create will, by default, use 2 factor authentication.  Accordingly for the time being, if you need new accounts created you should email Jisc help desk with the user's details requesting that the accounts be created for you."

CC_LIST = ["XXXX.YYYY@YYYY.ac.uk", "ZZZZ@jisc.ac.uk"]
BCC_LIST = []

with app.app_context():
    initialise()
    ### ALter config to avoid outputting DEBUG log messages
    app.config["LOGLEVEL"] = "INFO"
    app.config["LOG_DEBUG"] = False

    END_TEXT = f'<br><br>If you have any questions please don\'t hesitate to contact us at <a href="mailto:XXXX@YYYY.ac.uk?subject=Publications%20Router%20user%20account%20query">XXXX@YYYY.ac.uk</a>.<br><br>Regards'

    log_title(f"Send password reset emails to users")
    mail_account = MailAccount()
    subject = "Your new Publications Router user account"
    num_sent = 0
    # For ALL undeleted user accounts
    for user_acc in AccUser.pull_all("RSAJD", pull_name="undeleted_of_type", for_update=True):
        to_addr = user_acc.username
        if "@" in to_addr:
            num_sent += 1
            user_acc.direct_login = True
            user_acc.update()
            if user_acc.is_admin:
                email_body = EMAIL_KNOWN.format(user_acc.forename, user_acc.surname) +  TWO_STAGE + ADMIN_EXTRA + END_TEXT
            elif user_acc.surname == "User":
                email_body = EMAIL_UNKNOWN + TWO_STAGE + END_TEXT
            else:
                email_body = EMAIL_KNOWN.format(user_acc.forename, user_acc.surname) +  TWO_STAGE + END_TEXT
            # Construct the email message
            email = MailMsg(subject, "mail/contact.html", msg=email_body, error_msg_tuples=[])
            mail_account.send_mail([to_addr], cc=CC_LIST, bcc=BCC_LIST, msg_obj=email)
            log_msg("INFO", f"Email sent to user <{user_acc.forename} {user_acc.surname}> at {to_addr}.")
        else:
            log_msg("WARN", f"Email NOT sent to user <{user_acc.forename} {user_acc.surname}> because username ({to_addr}) is NOT an email.")

    log_title(f"ALL DONE - {num_sent} emails sent")
