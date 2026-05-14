#!/usr/bin/env python3
"""
Script to set/unset direct-login for all user accounts
"""
from octopus.core import initialise
from octopus.lib.mail import MailMsg, MailAccount
from router.jper.web_main import app     # need to import app_decorator as other modules import it from here.
from router.shared.models.account import AccUser

DIRECT_LOGIN = False
ACC_ROLE_CODES = "RSAJ"  # "RSAJD"

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

TWO_STAGE = "Following the teething problems with the new 2 stage authentication process (where the emailed login-link didn't work for many users), we have now changed to an access code mechanism. <br><br>Now, after you have entered valid credentials, an email will be sent to you containing an access code which you must enter (copy/paste) into a new field on the login screen."
ADMIN_EXTRA = "<br><br>Because the revised mechanism does not rely on an embedded link it should work in all circumstances - hence, as an administrator, you can create new user accounts for others in your organisation without fear of them encountering login problems."

CC_LIST = ["XXXX.YYYY@YYYY.ac.uk"]
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
    for user_acc in AccUser.pull_all(ACC_ROLE_CODES, pull_name="undeleted_of_type", for_update=True):
        to_addr = user_acc.username
        if "@" in to_addr:
            num_sent += 1
            user_acc.direct_login = DIRECT_LOGIN
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

            log_msg("INFO", f"Direct login set to {DIRECT_LOGIN} for user <{user_acc.forename} {user_acc.surname}>. Emailed: {to_addr}.")
        else:
            log_msg("WARN", f"Direct login NOT set for user <{user_acc.forename} {user_acc.surname}>.")

    log_title(f"ALL DONE - {num_sent} accounts set")
