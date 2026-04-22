#!/usr/bin/env python3
"""
Script to send password reset emails to new Users.
"""

from flask import url_for
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


EMAIL_KNOWN = "Dear {} {}<br><br>As detailed in recent emails to your organisation, Publications Router now has individual accounts for each user.<br><br>An {} has been created for you.  You should create a new password at the earliest opportunity using this link: {}."
EMAIL_UNKNOWN = "Dear User<br><br>As detailed in recent emails to your organisation, Publications Router now has individual accounts for each user.<br><br>As we don't have an email address for a particular person, a standard {} has been created for your organisation.  A new password can be created using this link: {}."
TWO_STAGE = "<br><br>Router now uses two stage authentication: after you have entered valid credentials (username & password), Router will email you a login link containing a onetime token.  You will be logged into your account when you click this link or paste it into your browser."
ADMIN_EXTRA = "<br><br>As an organisation administrator you are able to create and administer Router accounts for other people in your organisation."
ADMIN_END_TEXT_INSERT = ', <br>&nbsp; • <i>List users</i> - which shows all users in your organisation, from where you can select and administer other accounts,<br>&nbsp; • <i>Add user</i> - for adding a new user'

CC_LIST = ["XXXX.YYYY@YYYY.ac.uk", "ZZZZ@jisc.ac.uk"]
BCC_LIST = []

with app.app_context():
    initialise()
    ### ALter config to avoid outputting DEBUG log messages
    app.config["LOGLEVEL"] = "INFO"
    app.config["LOG_DEBUG"] = False

    END_TEXT = f'<br><br>The link for Publications Router is: {url_for("index")}.  Once you have logged in your will see the <i>My Account</i> menu tab, under which are now listed:<br>&nbsp; • <i>Organisation account</i> - which displays your organisation details, <br>&nbsp; • <i>User account</i> - which displays your user details{{}}.<br><br>If you have any questions please don\'t hesitate to contact us at <a href="mailto:XXXX@YYYY.ac.uk?subject=Publications%20Router%20user%20account%20query">XXXX@YYYY.ac.uk</a>.<br><br>Regards'

    log_title(f"Send password reset emails to users")
    mail_account = MailAccount()
    subject = "Your new Publications Router user account"
    num_sent = 0
    # For ALL undeleted user accounts
    for user_acc in AccUser.pull_all("RSAJD", pull_name="undeleted_of_type"):
        to_addr = user_acc.username
        if "@" in to_addr:
            num_sent += 1
            reset_token = user_acc.reset_token
            reset_token = reset_token.get("value", "") if reset_token else ""
            pwd_reset_url = url_for("account.reset_password", user_uuid=user_acc.uuid, token_val=reset_token, _external=True)
            username_text = f"account with username: <b>{to_addr}</b>"
            if user_acc.is_admin:
                email_body = EMAIL_KNOWN.format(user_acc.forename,
                                                user_acc.surname,
                                                "administrator " + username_text,
                                                pwd_reset_url
                                                ) + TWO_STAGE + ADMIN_EXTRA + END_TEXT.format(ADMIN_END_TEXT_INSERT)
            elif user_acc.surname == "User":
                email_body = EMAIL_UNKNOWN.format(username_text,
                                                  pwd_reset_url
                                                  ) + TWO_STAGE + END_TEXT.format("")
            else:
                email_body = EMAIL_KNOWN.format(user_acc.forename,
                                                user_acc.surname,
                                                username_text,
                                                pwd_reset_url
                                                ) + TWO_STAGE + END_TEXT.format("")
            # Construct the email message
            email = MailMsg(subject, "mail/contact.html", msg=email_body, error_msg_tuples=[])
            mail_account.send_mail([to_addr], cc=CC_LIST, bcc=BCC_LIST, msg_obj=email)
            log_msg("INFO", f"Email sent to user <{user_acc.forename} {user_acc.surname}> at {to_addr}.")
        else:
            log_msg("WARN", f"Email NOT sent to user <{user_acc.forename} {user_acc.surname}> because username ({to_addr}) is NOT an email.")

    log_title(f"ALL DONE - {num_sent} emails sent")
