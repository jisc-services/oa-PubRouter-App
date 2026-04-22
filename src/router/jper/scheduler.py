"""
This is the application scheduler, which defines scheduled tasks and runs them.

This scheduler must be started manually / managed by supervisor.

It is designed to run on App1 & (optionally) App2 server - BUT, certain batch services (move_ftp & processftp)
can be run ONLY on the SFTP server (App1).

POSSIBLE SCHEDULED JOBS:
* Notification submission related processing:
    1. move_ftp_from_jail_to_temp - moves FTP deposits from publisher's "Jail" directories to temporary process directory
    2. processftp - process FTP deposits, creating unrouted notifications and saving file packages in the Store
    3. route - Attempt to match unrouted notifications to repositories; convert to 'routed' if matched
    4. route_harv - Attempt to match harvested_unrouted notifications to repositories; if matched insert into notifications table
    5. sword_out - Send notifications to repositories (this only used in scheduler if sword_out NOT running as separate application)
* Batch (daily) jobs
    * delete_old - Delete old records from database
    * delete_files - Delete old files from filesystem directories
* Monthly jobs:
    * monthly_jobs - Monthly reporting

SCALING UP CONSIDERATIONS (i.e. running scheduler on multiple machines):
* There is a task that moves files from ftp user jail directories to tmp processing locations,
    and this is the limitation - creating sftp accounts has to happen on one machine or across machines,
    but that would increase attack surface for security vulnerability.
* So probably better to have only one machine open to sftp, and if necessary for later scale the script
    that is called to move data from the sftp jails to processing locations could do so by round-robin
    to multiple processing machines.
* Also, each machine running the schedule would need access to any relevant directories.

Author: Jisc
"""
import getpass
import os
import shutil
import time
import uuid
import errno
from sys import platform, argv
from datetime import date, datetime, timezone
from dateutil.relativedelta import relativedelta
# from flask import current_app
# from octopus.lib.scheduling import construct_process_map, init_and_run_schedule
from octopus.lib.killer import ProcessKilled, StandardGracefulKiller
from octopus.lib.data import truncate_string
from octopus.lib.shellscript import run_script_get_str_output, run_script_return_err_code
from octopus.core import initialise, add_extra_config, print_config_vals
from octopus.modules.mysql.dao import DAO, DAOException
from octopus.lib.mail import MailMsg, MailAccount
from router.shared import mysql_dao
from router.shared.shellscript import full_script_path
from router.shared.models.schedule import construct_process_map, Schedule, JobResult, NoJobsScheduled
from router.shared.models.note import UnroutedNotification, HarvestedNotification
from router.shared.models.account import AccOrg
from router.shared.models.harvester import HarvesterWebserviceModel
from router.shared.models.metrics import MetricsRecord
from router.shared.after_run_actions import database_reset, after_run_action
from router.jper.app import app, app_decorator
from router.jper import reports
from router.jper.forms.reports import MiscReportScriptsForm
from router.jper.api import JPER
from router.jper.models.publisher import FTPDepositRecord
from router.jper.models.reports import MonthlyInstitutionStats, MonthlyPublisherStats, MonthlyHarvesterStats
from router.jper.packages import FTPZipFlattener
from router.jper.routing import route
from router.jper.pub_testing import PubTesting, CRITICAL, ERROR, INFO, DEBUG
from router.jper.validate_route import auto_testing_validation_n_routing
# account blueprint below is imported so that above app can be imported from router.jper.app, instead of from
# router.jper.web_main which would involve importing & initialising a lot of unnecessary other blueprints
from router.jper.views.account import blueprint as account

app.jinja_env.trim_blocks = True
app.jinja_env.lstrip_blocks = True

# There were problems with memory leak, but these seem to have been fixed by Router Release 2.7.0 (February 2023)
# Even so, this code is retained in case further issues arise & memory tracing is again required
trace_memory = app.config.get("MEM_TRACE")
if trace_memory:
    from router.shared import mem_trace  # MMM

try:
    # Blueprint Needed because an email template used by PubTesting uses url_for('account.test_record', ...)
    app.register_blueprint(account, url_prefix="/account")
except ValueError:
    # This exception occurs when running all pytests because it doesn't seem to flush imports between successive test files
    # and web_main.py performs the same registration
    pass

# Self defined shell-script exit codes used by moveFTPfiles.sh and moveAtyponFTPfiles.sh
SIGNED_IN_EXIT_CODE = 5         # exit code returned if an SFTP user is still depositing files while we try to move them
MISSING_USER_EXIT_CODE = 6      # exit code returned if the user account does not appear in /etc/passwd file
BAD_ATYPON_FILE = 7             # exit code returned if problem with Atypon zip file


def _kill_old_sftp_processes():
    """
    Process that uses a shell script to kill sftpusers SFTP processes that are still running after X hours.

    :return: nothing
    """
    cutoff_hours = app.config.get("SFTP_KILL_AFTER_X_HOURS")
    if cutoff_hours:
        logfile = app.config.get("SFTP_KILL_LOG", "")
        result = run_script_return_err_code(full_script_path("kill_sftp.sh"), str(cutoff_hours), logfile)
        if result != 0:
            # If return code is 3, then there was a problem with params passed to the shellscript, otherwise some other OS error
            app.logger.critical("Shellscript 'kill_sftp.sh' failed with {}{}.".format(
                "a parameter problem" if result == 3 else "an OS error",
                f" (see log {logfile} for more details)" if logfile else ""))



def _unix_user_exists(user_uuid):
    """
    Confirm that Unix user exists.
    :param user_uuid: Unix user name
    :return: Boolean True - user exists; False - user does not exist
    """
    result = run_script_return_err_code(full_script_path("checkUserExists.sh"), user_uuid)
    if result == 0 or platform == 'win32':
        return True  # If running in Windows (i.e. Dev) environment then ignore issue, assume user exists
    else:
        app.logger.critical(f"User '{user_uuid}' has no UNIX account (in /etc/passwd).")
        return False


def _ftp_in_progress(user_uuid):
    """
    Check whether an active SFTP session is in progress for a particular unix user.
    :param user_uuid: Unix user name
    :return: Boolean True - FTP session is in progress; False - no FTP session in progress
    """
    result = run_script_return_err_code(full_script_path("checkFtpSessionExists.sh"), user_uuid)
    return result != 0  # Return code 0 means FTP connection not found


def _init_ftp_deposit_record(dir_or_file, pub_test):
    """
    Initialise either an FTPDepositRecord or PubTestRecord object.

    :param dir_or_file: Directory or file name
    :param pub_test: publisher testing object

    :return: FTPDepositRecord object or None
    """
    if pub_test.is_active():
        pub_test.new_submission(dir_or_file)
        return None
    else:
        pub_test.set_filename(dir_or_file)      # Filename may be used in error situations
        return FTPDepositRecord({
            "pub_id": pub_test.acc.id,
            "name": dir_or_file,
            "successful": False,
            "matched": False,
            "error": None
        })


def _log_error_and_save_deposit_rec(deposit_rec, msg, user_msg, pub_test):
    """
    If we have an error, save the error in the test_deposit_record or pub_deposit_record
    and then log the error.

    :param deposit_rec: Record to update & save
    :param msg: Error message to log
    :param user_msg: (optional) Error message more readable for users
    :param pub_test: publisher testing object

    :return: nothing
    """
    if not user_msg:
        user_msg = msg
    if pub_test.is_active():
        pub_test.create_test_record_and_finalise_autotest(user_msg)
    else:
        # record in the pub_deposit_record database the human-readable error message if there is one
        deposit_rec.error = user_msg
        deposit_rec.insert()
        _acc = pub_test.acc
        _acc.send_email(f"Publications Router submission error - file '{pub_test.filename}'",
                        user_msg,
                        to=_acc.TECHS,
                        email_template="mail/pub_error.html",
                        filename=pub_test.filename,
                        save_acc_email_rec=True
                        )
    pub_test.log(CRITICAL, msg, save=False, extra={"subject": "File submission"})


def _move_files_from_ftp_jail_dir(file_type, shell_script_name, source_xfer_path, pub_uuid, ftptmp_path,
                                  tmp_archive_path, pub_test):
    """
    Calls shellscript to move file from ftp jail directory to target temporary (processing) directory.

    IMPORTANT NOTES:
    * any exceptions, such as "out of disk space", are intended to be caught at a higher level by the calling function
    * some errors must always be reported to the main scheduler log (app.logger), others will be reported
      the pulisher-testing log - that is why `pub_test.log()` is used in some places - it determines which log
       to output to.

    :param file_type: string type of file: "regular"|"atypon"
    :param shell_script_name: name of shellscript.
    :param source_xfer_path: xfer or atypon_xfer dir in user's folder.
    :param pub_uuid: uuid of account and also the user's directory name
    :param ftptmp_path: ftptmp dir.
    :param tmp_archive_path: Safety dir for problematic files.
    :param pub_test: publisher testing object

    :return: Int - number of files moved
    """
    num_files = 0
    xfer_dir_listing = None
    try:
        xfer_dir_listing = os.listdir(source_xfer_path)
    except FileNotFoundError:
        app.logger.critical(f"move_ftp: Cannot list directory: {source_xfer_path}")

    # If files to move
    if xfer_dir_listing:
        # Check if an FTP connection exists immediately before getting directory listing, and if it does
        # set latest_allowed_file_modified_time_secs to X seconds before the current time
        if _ftp_in_progress(pub_uuid):
            msg = "Active FTP connection for "
            minimum_secs_since_last_modified = app.config.get("ACTIVE_FTP_MIN_SECS_SINCE_LAST_MODIFIED")
            # Processing of files while an active FTP connection is allowed for files older than X seconds
            if minimum_secs_since_last_modified:
                msg2 = ""
                # Set 'latest allowed time' value to X seconds ago; any file with 'last modified time' older than that
                # will be moved; any file more recent than that will not be moved
                latest_allowed_file_modified_time_secs = int(time.time()) - minimum_secs_since_last_modified
            else:  # No processing of files while there is an active FTP connection
                msg2 = "NOT "
                # Setting to None prevents moving any files (because an FTP connection exists)
                latest_allowed_file_modified_time_secs = None
        else:
            msg = msg2 = ""
            # Value 0 indicates that last-modified time is not of interest (where no FTP connection exists)
            latest_allowed_file_modified_time_secs = 0
    
        acc_org_name = pub_test.acc.org_name
        acc_id = pub_test.acc.id
        pub_test.log(INFO, f"move_ftp: {msg}Acc: '{acc_org_name}' (ID:{acc_id}, UUID:{pub_uuid}) - {msg2}Processing {len(xfer_dir_listing)} {file_type} files.")

        # If FTP file processing is allowed
        if latest_allowed_file_modified_time_secs is not None:
            move_files_script = full_script_path(shell_script_name)
            # Get the username of the owner who will now own the files after moving the files
    
            newowner = 'jenkins'        # In UNIX environment (default value)
            # If not UNIX environment, obtain application owner name
            if not app.config.get("UNIX_FTP_ACCOUNT_ENABLE"):
                try:
                    newowner = getpass.getuser()
                except:
                    pass
    
            bad_file_count = 0
            for item in xfer_dir_listing:
                item_full_path = f"{source_xfer_path}/{item}"
                # if latest_allowed_file_modified_time_secs is non-zero it means an active FTP connection was detected
                if latest_allowed_file_modified_time_secs:
                    # If file last modified time is later than the latest allowed time then don't process it
                    if int(os.path.getmtime(item_full_path)) > latest_allowed_file_modified_time_secs:
                        pub_test.log(INFO,
                                     f"move_files…: Skipped recent file '{item}' as FTP connection exists; Acc: {pub_uuid}."
                                     )
                        continue
    
                pub_test.log(INFO, f"move_files…: Moving {file_type} file '{item}' for Acc: {pub_uuid}  (New owner: {newowner}).")
                uniqueid = uuid.uuid4().hex
    
                # Call the move_files shell script with params username (=dir), new-owner,
                #   temporary directory, unique-id, file-to-move, [ optional safety-directory ]
                ret_code = run_script_return_err_code(move_files_script,
                                                      pub_uuid,  # 1
                                                      newowner,  # 2
                                                      ftptmp_path,  # 3 - target temporary directory
                                                      uniqueid,  # 4
                                                      item_full_path,  # 5 - File being moved
                                                      tmp_archive_path  # 6 - Temp archive directory
                                                      )
                if ret_code == 0:   # All is OK
                    num_files += 1
                elif ret_code == BAD_ATYPON_FILE:
                    user_msg = f"Atypon file '{item}' has incorrect format"
                    msg = f"{user_msg}. File is in tmparchive: {tmp_archive_path}/{pub_uuid}/{uniqueid}"
                    # Need to record bad atypon file in ftp-deposit-record here, because (unlike regular FTP deposits)
                    # it will have just been deleted by the shell script and it will not be subsequently processed.
                    _log_error_and_save_deposit_rec(_init_ftp_deposit_record(item, pub_test),
                                                    msg, user_msg, pub_test)
                    bad_file_count += 1
                else:
                    # Some other error. It's probably a no space error, so just return that.
                    raise OSError(errno.ENOSPC, "No space left on device")
    
            # If any bad Atypon files found, then log error
            if bad_file_count:
                msg = f"{bad_file_count} failures occurred while processing {len(xfer_dir_listing)} {file_type} files" \
                      f" in directory '{source_xfer_path}' for Acc: '{acc_org_name}' (ID:{acc_id}, UUID:{pub_uuid}). (See log for individual details)."
                pub_test.log(ERROR, msg, save=False)

    return num_files


def _move_files_to_error_dir(user_uuid, origin_files_dir):
    """
    If we have an error, move the file to ftperrors folder.

    :param user_uuid: User UUID, which is also name of user's directory
    :param origin_files_dir: origin directory to move
    """

    save_dir = os.path.join(app.config.get("FTP_ERROR_DIR", "/Incoming/ftperrors"), user_uuid)
    save_files_dir = os.path.join(save_dir, os.path.basename(origin_files_dir))

    try:
        # If the directory doesn't already exist, make target directory;
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)

        shutil.move(origin_files_dir, save_files_dir)

    except Exception as e:
        app.logger.critical(
            f"Problem creating directory '{save_files_dir}' or moving '{origin_files_dir}' to it - {repr(e)}",
            exc_info=True
        )


def _create_unrouted_notification_from_ftp_deposit(this_dir, pub_acc, pub_test):
    """
    Processes the contents of a directory that should contain a SINGLE notification (package deposit) received via FTP.
    The notification will be in either a directory or a zip file.

    :param this_dir: Dir we are working in
    :param pub_acc: Acc this dir relates to
    :param pub_test: publisher testing object
    """

    def _format_err_msgs(base_msg, dir_or_file, org_name, acc_id, e):
        """
        Constructs 2 error messages - a long one and a short version.
        :param base_msg: Error msg, which will have " 'dir-or-file'" appended if dir_or_file has a value
        :param dir_or_file: directory or filename
        :param org_name: organisation name
        :param acc_id: account id
        :param e: exception
        :return: Tuple: full-message, user-message
        """
        if dir_or_file:
            base_msg += f" '{dir_or_file}'"
        return (f"_create_unrouted…: {base_msg} from '{org_name}' ({acc_id}) - {repr(e)}.",
                f"{base_msg} - {str(e)}")

    # Note we expect only ONE item to be returned by listdir
    for dir_or_file in os.listdir(this_dir):
        # Publisher should have deposited a zip file, but may have deposited a directory containing files.

        # Create FTP record to store a record of this publisher's submission
        ftp_record = _init_ftp_deposit_record(dir_or_file, pub_test)

        # should be one directory or zip-file per publication notification - that is what they are told to provide
        # if it is a file then dump it into a directory so it can be zipped easily
        notification_dir = os.path.join(this_dir, dir_or_file)
        if os.path.isfile(notification_dir):
            # At this point we have a file: this will be moved into a new directory (with a hex name)
            try:
                # Make a new directory to hold the file
                new_dir = uuid.uuid4().hex
                new_sub_dir = os.path.join(this_dir, new_dir)
                os.makedirs(new_sub_dir)

                # Move file into new directory
                shutil.move(notification_dir, new_sub_dir + "/")

                # Reset notification_dir from the filename path to the new directory path
                notification_dir = new_sub_dir
            except Exception as e:
                message, user_msg = _format_err_msgs(
                    f"Problem making directory '{new_sub_dir}' or moving file '{notification_dir}' to it",
                    None, pub_acc.org_name, pub_acc.id, e)
                _log_error_and_save_deposit_rec(ftp_record, message, user_msg, pub_test)
                raise Exception('Moving notification file') from e

        # by now this should look like this:
        # /Incoming/ftptmp/<user-uuid>/<transaction-uuid>/<uploaded-dir-OR-uuid-dir>/<thing-that-was-uploaded>

        # they should provide a directory of files or a zip, but it could be just one file
        # but we don't know the hierarchy of the content, so we have to unpack and flatten it all
        # unzip and pull all docs to the top level then zip again. Should be JATS file at top now
        notification_zip_file = notification_dir + '.zip'
        try:
            app.logger.info(f"Processing FTP deposit '{dir_or_file}' for Acc: '{pub_acc.org_name}' (ID:{pub_acc.id}, UUID:{pub_acc.uuid})")
            flattener = FTPZipFlattener(
                notification_dir, pub_test, max_zip_size=app.config.get("MAX_ZIP_SIZE"), large_zip_size=app.config.get("LARGE_ZIP_SIZE"))
            flattener.process_and_zip(notification_zip_file)
        except Exception as e:
            message, user_msg = _format_err_msgs("Error flattening FTP deposit file", dir_or_file, pub_acc.org_name, pub_acc.id, e)
            _log_error_and_save_deposit_rec(ftp_record, message, user_msg, pub_test)
            raise Exception('Flattening notification directory') from e

        # PREVIOUSLY: an unrouted-notification was created by sending details via PubRouter API, but for performance
        # reasons this was replaced by direct creation.
        # create basic notification metadata and create the notification from that and the zip file
        basic_note_dict = {
            "vers": app.config.get("API_VERSION"),
            "provider": {"route": "ftp"},
            "content": {"packaging_format": "https://pubrouter.jisc.ac.uk/FilesAndJATS"}
        }
        if pub_test.is_active():
            # the zip file exists on local server, so we can just pass the file pathname
            auto_testing_validation_n_routing(pub_test, basic_note_dict, note_zip_file=notification_zip_file)
        else:
            try:
                # The zip file exists on local server, so we can just pass the file pathname
                note = JPER.create_unrouted_note(pub_acc, basic_note_dict, file_path=notification_zip_file, orig_fname=pub_test.filename)

                # This line will only be reached if the note exists, as we are definitely using a publisher account -
                # create_unrouted_note can return False if `acc` is not a publisher, but it always will be.
                ftp_record.notification_id = note.id
                ftp_record.successful = True
                ftp_record.insert()
            except Exception as e:
                # Failed to create unrouted-notification
                message, user_msg = _format_err_msgs("Failed to create notification from file", dir_or_file, pub_acc.org_name, pub_acc.id, e)
                _log_error_and_save_deposit_rec(ftp_record, message, user_msg, pub_test)
                raise e


def _send_report_emails(report_year, report_month, **report_files):
    """
    Sends emails to respective config defined email address lists, each email address will receive different
    reports dependent on config settings. Email address config looks like
        {
            "email_address@address.com": ["publisher", "harvester", "institutions_test"],
            "email_address2@address.com": ["publisher", "institutions_live"]
        }
    email_address@address.com will receive the publisher, harvester and test institutions reports, and
    email_address2@address.com will receive only the publisher and live institutions reports.

    :param report_year: Year of report
    :param report_month: Month of report
    :param report_files: Kwargs of config variable names to the file names of various reports. Ex:
        _send_report_files(2018, 12, publisher=publisher_report_file, harvester=harvester_report_file...).
    """

    if app.config.get("LOG_DEBUG"):
        app.logger.debug("_send_report_emails: Sending report emails")
    # format of the email's subject
    email_subject_format = app.config.get("EMAIL_SUBJECT_REPORTS_FORMAT")
    mail_account = MailAccount()
    # email addresses dictionary of format { "email_address": [list of report types], "email_addr.... }
    email_address_dict = app.config.get("REPORT_EMAIL_ADDRESSES")
    # each email address has an associated list of report types to send with it
    for email_address, report_types in email_address_dict.items():
        app.logger.info(f"_send_report_emails: Sending email to {email_address} with report types: {report_types}")
        email = MailMsg(
            email_subject_format.format(report_year, str(report_month).zfill(2)),
            "mail/reports.html",
            report_types=report_types,
            # attachments=[MailMsg.create_attachment(report_files.get(report_type)) for report_type in report_types]
            files=[report_files.get(report_type) for report_type in report_types]
        )
        mail_account.send_mail([email_address], msg_obj=email)


def _send_individual_report_emails(email_template, subject_template, email_tuple_list, bcc_list=None, **kwargs):
    """
    Sends report by email.
    :param email_template: String - HTML template containing email text
    :param subject_template: String - Email subject line, may contain '{}' formatting placeholder for org_name
    :param email_tuple_list: List of Tuples [([recipient-email-list], file-path, org-name), ...]
    :param bcc_list: List of Strings - List of BCC email recipients
    :param kwargs: Optional args will be passed to email_template
    """
    mail_account = MailAccount()
    for to_list, report_file_path, org_name in email_tuple_list:
        if to_list:
            subject = subject_template.format(org_name)
            app.logger.info(f"_send_individual_report_emails: {subject} to {to_list}")
            email = MailMsg(
                subject,
                email_template,
                # attachments=[MailMsg.create_attachment(report_file_path)],
                files=[report_file_path],
                org_name=org_name,
                **kwargs
            )
            mail_account.send_mail(to_list, bcc=bcc_list, msg_obj=email)


def _create_monthly_statistics_records():
    """
    Inserts records into the following statistics tables for the month just passed:
        * monthly_institution_stats
        * monthly_publisher_stats
        * monthly_harvester_stats
        * monthly_publisher_doi_match_to_repos
    :return: Int - Total records created
    """
    last_month = datetime.now(tz=timezone.utc).date() - relativedelta(months=1)
    first_date = date(last_month.year, last_month.month, 1)
    last_date = first_date + relativedelta(day=31)      # Always sets correct last day of the month
    total_recs = 0
    try:
        # Create monthly_institution_stats records
        num_recs = MonthlyInstitutionStats.create_monthly_stats_records(first_date, last_date)
        app.logger.info(f"Monthly institution statistics record count: {num_recs}.")
        total_recs += num_recs
    except Exception as e:
        app.logger.critical(f"Monthly institution statistics records creation failed - {repr(e)}", exc_info=True)

    try:
        # Create monthly_publisher_stats records
        num_recs = MonthlyPublisherStats.create_monthly_stats_records(first_date, last_date)
        app.logger.info(f"Monthly publisher statistics record count: {num_recs}.")
        total_recs += num_recs
    except Exception as e:
        app.logger.critical(f"Monthly publisher statistics records creation failed - {repr(e)}", exc_info=True)

    try:
        # Create monthly_harvester_stats records
        num_recs = MonthlyHarvesterStats.create_monthly_stats_records(first_date, last_date)
        app.logger.info(f"Monthly harvester statistics record count: {num_recs}.")
        total_recs += num_recs
    except Exception as e:
        app.logger.critical(f"Monthly harvester statistics records creation failed - {repr(e)}", exc_info=True)
    return total_recs


def _generate_pub_doi_reports(for_month, reportsdir):
    """
    Generate publisher DOI reports for particular month
    :param for_month: DateTime object - month required
    :param reportsdir: Path to directory where reports are stored
    """
    try:
        publisher_doi_reports_dir = f"{reportsdir}/{app.config['PUB_DOI_REPORT']}"
        # Run from 1st day to last day of last month (day=31 will always translate to actual last day of month)
        reports_created_tuple_list = reports.generate_all_publisher_doi_to_repos_reports(
            for_month + relativedelta(day=1),
            for_month + relativedelta(day=31),
            publisher_doi_reports_dir
        )
        # Now email each report to recipients
        report_date = for_month.strftime('%B, %Y')
        _send_individual_report_emails("mail/pub_doi_report.html",
                                       f"Publications Router article distribution report for {report_date}. ({{}})",
                                       reports_created_tuple_list,
                                       bcc_list=app.config.get("REPORT_BCC"),
                                       report_date=report_date
                                       )
    except Exception as e:
        app.logger.critical(f"Publisher DOI report generation failed - {repr(e)}", exc_info=True)


def _monthly_reporting(reportsdir):
    """
    NOTE: Any change here should be replicated in rerunreportTestLive.py

    python schedule does not actually handle months, so this will run every day and check whether the current month
    has rolled over or not.

    """
    try:
        last_month = datetime.now(tz=timezone.utc).date() - relativedelta(months=1)
        report_month = last_month.month
        report_year = last_month.year
        first_date = date(report_year, 1, 1)  # Jan 1st
        last_date = date(report_year, 12, 1)  # Dec 1st

        # Create report files dict
        report_files = {}

        ### LIVE INSTITUTION REPORT ###
        csv_filename = f"{reportsdir}/LIVE_monthly_notifications_to_institutions_{report_year}.csv"
        try:
            reports.generate_institutions_report(first_date, last_date, csv_filename, live_file=True)
        except Exception as e:
            app.logger.critical(f"Institution Live report generation failed - {repr(e)}", exc_info=True)
        report_files["institutions_live"] = csv_filename

        ### TEST INSTITUTION REPORT ###
        csv_filename = f"{reportsdir}/TEST_monthly_notifications_to_institutions_{report_year}.csv"
        try:
            reports.generate_institutions_report(first_date, last_date, csv_filename, live_file=False)
        except Exception as e:
            app.logger.critical(f"Institution Test report generation failed - {repr(e)}", exc_info=True)
        report_files["institutions_test"] = csv_filename

        ### PUBLISHER REPORT ###
        publisher_reportsdir = f"{reportsdir}/publishers"
        csv_filename = f"{publisher_reportsdir}/monthly_notifications_from_publishers_{report_year}.csv"
        if not os.path.exists(publisher_reportsdir):
            os.makedirs(publisher_reportsdir)
        try:
            reports.generate_publisher_report(first_date, last_date, csv_filename)
        except Exception as e:
            app.logger.critical(f"Publisher report generation failed - {repr(e)}", exc_info=True)
        report_files["publisher"] = csv_filename

        ### HARVESTER REPORT ###
        csv_filename = f"{publisher_reportsdir}/monthly_notifications_from_harvester_{report_year}.csv"
        try:
            reports.generate_harvester_report(first_date, last_date, csv_filename)
        except Exception as e:
            app.logger.critical(f"Harvester report generation failed - {repr(e)}", exc_info=True)
        report_files["harvester"] = csv_filename

        ### DUPLICATE SUBMISSIONS REPORT (for the past month) ###
        dup_reports_dir = f"{reportsdir}/dup_submission"
        if not os.path.exists(dup_reports_dir):
            os.makedirs(dup_reports_dir)
        csv_filename = f"{dup_reports_dir}/duplicate_submissions_{last_month.strftime('%Y-%m')}.csv"
        try:
            reports.generate_duplicate_submissions_report((last_month + relativedelta(day=1)).strftime("%Y-%m-%d"),
                                                          (last_month + relativedelta(day=31)).strftime("%Y-%m-%d"),
                                                          csv_filename)
        except Exception as e:
            app.logger.critical(f"Duplicate submissions report generation failed - {repr(e)}", exc_info=True)
        report_files["dup_submission"] = csv_filename

        ### SEND REPORT EMAILS ###
        _send_report_emails(report_year, report_month, **report_files)


        ## Generate Publisher DOI reports ##
        _generate_pub_doi_reports(last_month, reportsdir)

    except Exception as e:
        app.logger.critical(f"Reporting job failed - {repr(e)}", exc_info=True)


def adhoc_report(report_type=None, email_to_list=None, org_name=None):
    """
    Execute long-running reports (provider_aff_usage_report, note_types_report) on an adhoc basis
    :param report_type: String - type of report to run
    :param email_to_list:  List of Strings - Email addresses or String - SINGLE email address
    :param org_name: [OPTIONAL] String - Organisation name
    :return: JobResult object
    """
    if report_type is None:
        return
    # Dict that maps report keyword to tuple: (function-name, kwargs)
    report_funcs = {
        "aff_analysis": (reports.provider_aff_usage_report, {}),
        "aff_org_analysis": (reports.provider_aff_org_report, {}),
        "note_analysis": (reports.note_types_report, {}),
    }
    try:
        report_fn, kwargs = report_funcs.get(report_type, (None, None))
        if report_fn is None:
            raise Exception(f"Report '{report_type}' is not supported.")

        if isinstance(email_to_list, str):
            email_to_list = [email_to_list]
        misc_reports_dir = os.path.join(app.config.get('REPORTSDIR', '/var/pubrouter/reports'), "misc")
        if not os.path.exists(misc_reports_dir):
            os.makedirs(misc_reports_dir)

        report_info = MiscReportScriptsForm.report_info.get(report_type)
        # The `report_info` tuple has following 5 elements:
        #   0 - Report summary (displayed as select field option)
        #   1 - Report description (added as title attribute to select field option)
        #   2 - Further information
        #   3 - Report name
        #   4 - Output filename for script (could contain '{}' placeholders if script can fill them)
        #   5 - Boolean flag indicates if report is run as a Batch (True) or Online (False) job
        filename = report_info[4]
        report_date = datetime.now().strftime("%Y-%m-%d")
        if "{" in filename:
            filename = filename.format(report_date)
        file_path = os.path.join(misc_reports_dir, filename)

        try:
            metrics = MetricsRecord(server=app.config.get("SERVER_ID", "Dev"), proc_name="Adhoc-Report", measure="rec")
            file_path, rec_count = report_fn(file_path, **kwargs)
            duration_secs = metrics.log_and_save(log_msg=". Scanned {} record{}", count=rec_count,
                                                 extra={report_type: ""})
        except Exception as e:
            raise Exception(f"Failed to run report: '{report_type}' - {repr(e)}.") from e

        try:
            report_name = report_info[3]
            _send_individual_report_emails("mail/misc_report.html",
                                           f"Publications Router report - {report_name} ({report_date})",
                                           [(email_to_list, file_path, org_name or "")],
                                           report_name=report_name,
                                           report_date=report_date,
                                           description=". ".join(report_info[0:2]),
                                           duration=f"{duration_secs} seconds"
                                           )
        except Exception as e:
            raise Exception(f"Failed to email report: '{report_type}' to '{email_to_list}' - {repr(e)}.") from e
    except Exception as e:
        app.logger.error(str(e), extra={"mail_it": True, "subject": "Adhoc report problem"})

    return JobResult(count=1)


def delete_old_files():
    """
    Deletes old files from filesystem.  Calls shell-scripts which used to be run as cron jobs.
    """
    def delete_store_files(script_path, process_name, store_dir, min_days_to_keep, days_to_keep):
        """
        Call script to delete files from particular directory.  Obtain count of items deleted from the scripts output
        to Stdout.
        :param script_path: String - path to shell-script that does deletion
        :param process_name: String - brief name of process WITHOUT any intervening spaces
        :param store_dir: String - String - Directory from which files are to be deleted
        :param min_days_to_keep: Integer - minimum number of days for file retention
        :param days_to_keep: Integer - actual number of days for file retention

        :return: Int - Count of items deleted
        """
        # Only delete if path exists on server
        items_deleted = 0
        if os.path.exists(store_dir):
            ret_code, output_str = run_script_get_str_output(
                script_path,
                process_name,  # Script param 1
                store_dir,  # Script param 2
                str(min_days_to_keep),  # Script param 3
                str(days_to_keep)  # Script param 4
                )
            if ret_code:  # None zero means error
                app.logger.critical(f"Problem deleting files [{process_name}] - Return code: {ret_code} - \n {output_str}")
            else:
                # We expect the shellscript to report: "... Number of files & folders deleted: 999."
                _, _, count = output_str.rpartition(":")
                items_deleted = int(count.strip(" .\n\t") or 0)  # Remove white-spaces and full-stop, & convert to integer
                app.logger.info(f"Successful file deletion [{process_name}] - {items_deleted} items - \n {output_str}")

        return items_deleted


    metrics = MetricsRecord(server=app.config.get("SERVER_ID", "Dev"), proc_name="Delete-Files", measure="file")
    total_deleted = 0
    deleted_counts = {}
    ## Delete files from following directories /Incoming/store & /var/pubrouter/local_store/tmp
    delete_files_script = full_script_path("delete_files.sh")
    # Delete from Temp store
    num_deleted = delete_store_files(
        delete_files_script,
        "delete_temp_store",
        app.config.get("STORE_TMP_DIR", "/var/pubrouter/local_store/tmp"),
        2,   # Minimum days to keep
        5   # Actual days to keep
        )
    deleted_counts["temp-store"] = num_deleted
    total_deleted += num_deleted

    # The Main file store exists only on the server with store-type "local"
    if app.config.get("STORE_TYPE") == "local":
        # Delete from Main store
        num_deleted = delete_store_files(
            delete_files_script,
            "delete_main_store",
            app.config.get("STORE_MAIN_DIR", "/Incoming/store"),
            30,   # Minimum days to keep
            92   # Actual days to keep
            )
        deleted_counts["main-store"] = num_deleted
        total_deleted += num_deleted

    # The /Incoming/ftperrors & /Incoming/tmparchive directories are only on the server which runs 'move_ftp' job
    if "move_ftp" in app.config.get("SCHEDULER_JOBS", []):
        delete_ftp_files_script = full_script_path("delete_old_ftp_files.sh")
        num_deleted = delete_store_files(
            delete_ftp_files_script,
            "delete_ftperrors",
            app.config.get("FTP_ERROR_DIR", "/Incoming/ftperrors"),
            7,   # Minimum days to keep
            app.config.get("FTP_ERROR_KEEP_DAYS", "28")   # Actual days to keep
            )
        deleted_counts["ftperrors"] = num_deleted
        total_deleted += num_deleted

        num_deleted = delete_store_files(
            delete_ftp_files_script,
            "delete_tmparchive",
            app.config.get("FTP_SAFETY_DIR", "/Incoming/tmparchive"),
            3,   # Minimum days to keep
            app.config.get("FTP_SAFETY_KEEP_DAYS", "7")   # Actual days to keep
            )
        deleted_counts["tmparchive"] = num_deleted
        total_deleted += num_deleted

    metrics.log_and_save(log_msg=". Deleted {} file{}", count=total_deleted, extra=deleted_counts)
    return total_deleted


def delete_old_data():
    """
    Deletes notifications, sword deposit records, match provenance data and other records
    older than X months ago (set in config - see SCHEDULED_DELETION_DICT) from database.
    """
    class_map = {
        # "table_name": DAO-Class
        "notification": mysql_dao.NotificationDAO,
        "content_log": mysql_dao.ContentLogDAO,
        "match_provenance": mysql_dao.MatchProvenanceDAO,
        "pub_deposit": mysql_dao.PubDepositRecordDAO,
        "pub_test": mysql_dao.PubTestRecordDAO,
        "sword_deposit": mysql_dao.SwordDepositRecordDAO,
        "h_errors": mysql_dao.HarvErrorRecordDAO,
        "h_history": mysql_dao.HarvHistoryRecordDAO,
        "acc_repo_match_params_archived": mysql_dao.AccRepoMatchParamsArchivedDAO,
        "acc_bulk_email": mysql_dao.AccBulkEmailDAO,
        "acc_notes_emails": mysql_dao.AccNotesEmailsDAO,
        "cms_html": mysql_dao.CmsHtmlDAO,
        "metrics": mysql_dao.MetricsRecordDAO
    }
    if app.config.get("LOG_DEBUG"):
        app.logger.debug('Scheduler delete_old_data: Checking for index records to delete')
    metrics = MetricsRecord(server=app.config.get("SERVER_ID", "Dev"), proc_name="Delete-Data", measure="rec")
    total_deleted = 0
    table_deleted_counts = {}
    try:
        # Get timestamp for today, with HH:MM:SS set to 0:0:0
        today = datetime.now(tz=timezone.utc).date()
        # Loop for each entry of the SCHEDULED_DELETION_DICT which contains 2 element tuples
        # {"table-name": ("deletion-query-name", number-months-to-keep), ...}
        for table_name, (del_name, keep_months) in app.config.get("SCHEDULED_DELETION_DICT", {}).items():
            dao_class = class_map[table_name]
            older_than_date = today - relativedelta(months=keep_months)
            # Cursor is closed after use as used infrequently (once per day)
            num_deleted = dao_class.delete_by_query(older_than_date, del_name=del_name, close_cursor=True)
            table_deleted_counts[table_name] = num_deleted
            total_deleted += num_deleted
            app.logger.info(
                f"delete_old_data: Deleted {num_deleted} records older than {keep_months} months from {table_name} table"
            )
    except Exception as e:
        app.logger.critical(f"Failed scheduled database table record deletion - {repr(e)}", exc_info=True)

    metrics.log_and_save(log_msg=". Deleted {} record{}", count=total_deleted, extra=table_deleted_counts)
    return total_deleted


def move_ftp_from_jail_to_temp():
    """
    Step 1 in Router FTP process flow (1.move_ftp_from_jail_to_temp --> 2.processftp --> 3.check_unrouted)

    Moves any files from each publishers FTP jail directories (xfer and atypon_xfer) into a temporary
    location for subsequent processing.

    Each publisher has their own directory (named with their Router ID) in the temporary location and files will be
    moved into subdirectories beneath that.

    It also keeps a copy of each file in the temporary archive folder (from where they are deleted by cron job).

    For normal deposits in xfer directory, it makes a call to the moveFTPfiles.sh to move the files into FTPTMP (into
    publishers subdirectory).
    This is because the script needs to be run as root and the user running scheduler may have insufficient permissions
    to create directories and move the files.

    It similarly  moves the atypon deposit files, using moveAtyponFTPfiles.sh. This will unzip an Atypon zip file,
    then zip each folder that it contains (below the main issue folder) and place them in FTPTMP.

    :return: Count of files moved
    """
    metrics = MetricsRecord(server=app.config.get("SERVER_ID", "Dev"), proc_name="Move-FTP", measure="file")
    files_moved = 0
    PubTesting.init_pub_testing_class(init_mail=True)
    err_msg = "Move from FTP failed for Account {}{} - {}"
    pub_uuid = ''
    try:
        # Kill sftpusers SFTP processes that are still running after X hours.
        _kill_old_sftp_processes()

        # If set holds a (permanent) copy of each file received via FTP
        tmp_archive_path = app.config.get('FTP_SAFETY_DIR', '/tmp/archive')
        ftptmp_path = app.config.get('FTP_TMP_DIR', '/Incoming/ftptmp')
        users_dir = app.config.get('USERDIR', '/home/sftpusers')
        pub_dirs = os.listdir(users_dir)
        if app.config.get("LOG_DEBUG"):
            app.logger.debug(f"move_ftp: Checking {len(pub_dirs)} user directories")
        # Loop for each publisher user directory (directory name == account id)
        for pub_uuid in pub_dirs:
            pub_acc = AccOrg.pull(pub_uuid, pull_name="uuid")
            # only move ftps for accounts which exist & are turned on and the user account exists on the server
            if pub_acc:
                if not pub_acc.publisher_data.is_deactivated():
                    if _unix_user_exists(pub_uuid):
                        pub_test = PubTesting(pub_acc, "ftp")

                        # For both xfer and atypon_xfer directories, check for files to move, and move them
                        for file_type, xfer_dir, move_files_shell_script in (("regular", "xfer", "moveFTPfiles.sh"),
                                                                             ("atypon", "atypon_xfer", "moveAtyponFTPfiles.sh")):
                            # Directory where users will have deposited files
                            source_xfer_path = f"{users_dir}/{pub_uuid}/{xfer_dir}"

                            files_moved += _move_files_from_ftp_jail_dir(
                                file_type, move_files_shell_script, source_xfer_path, pub_uuid, ftptmp_path, tmp_archive_path, pub_test)
                    else:
                        app.logger.error(f"move_ftp: Expected UNIX account doesn't exist: {pub_uuid}")
                else:
                    if app.config.get("LOG_DEBUG"):
                        app.logger.debug(f"move_ftp: Account is deactivated: '{pub_acc.org_name}' (ID:{pub_acc.id}, UUID:{pub_acc.uuid})")
            else:
                app.logger.error(f"move_ftp: Expected account db record doesn't exist: {pub_uuid}")

    except OSError as e:
        # if we have an OSError w/ no space error code
        if e.errno == errno.ENOSPC:
            # don't make this critical, as it's an "expected error" and will send many emails and spam the inbox
            app.logger.error(err_msg.format(pub_uuid, ' - /Incoming FULL', repr(e)))
        else:
            app.logger.critical(err_msg.format(pub_uuid, '', repr(e)), exc_info=True)
    except Exception as e:
        app.logger.critical(err_msg.format(pub_uuid, '', repr(e)), exc_info=True)

    metrics.log_and_save(log_msg=". Moved {} file{}", count=files_moved)
    return files_moved


def processftp():
    """
    Step 2 in Router FTP process flow (1.move_ftp_from_jail_to_temp --> 2.processftp --> 3.check_unrouted)

    Processes all FTP files that are sitting in each Publisher's temporary FTPTMP directory (they will have been moved
    here by previous process).  From each of these create an "unrouted notification".

    :return: nothing
    """
    proc_ftp_killer = StandardGracefulKiller(app.logger, "Process FTP")
    metrics = MetricsRecord(server=app.config.get("SERVER_ID", "Dev"), proc_name="Process-FTP", measure="file")
    num_processed = 0
    num_ok = 0
    PubTesting.init_pub_testing_class(init_mail=True)
    this_dir = ''
    try:
        # list all directories in the temp dir - one for each ftp user for whom files have been moved from their jail
        ftp_files_source_root_dir = app.config.get('FTP_TMP_DIR', '/tmp')
        publisher_dirs_list = os.listdir(ftp_files_source_root_dir)
        if app.config.get("LOG_DEBUG"):
            app.logger.debug(f"processftp: Found {len(publisher_dirs_list)} temp user directories")

        # Process each Publisher's folder - NOTE that the directory name == publisher acc ID
        for pub_uuid in publisher_dirs_list:
            if proc_ftp_killer.killed:
                break
            pub_acc = AccOrg.pull(pub_uuid, pull_name="uuid")
            if pub_acc is None:
                app.logger.error("Process FTP - Account not found for user directory: " + pub_uuid)
                continue
            pub_test = PubTesting(pub_acc, "ftp")
            # List the content's of the Publisher's (temporary) FTP directory - it will contain a set of
            # subdirectories or zip-files, each being a deposited notification.  (These will have previously been
            # moved here from the user's FTP jail directory by a separate process)
            user_directory = os.path.join(ftp_files_source_root_dir, pub_uuid)
            for udir in os.listdir(user_directory):
                if proc_ftp_killer.killed:  # Interrupt occurred during processing
                    break
                this_dir = os.path.join(user_directory, udir)
                if app.config.get("LOG_DEBUG"):
                    pub_test.log(DEBUG, f"processftp: Processing {this_dir} for Acc: '{pub_acc.org_name}' (ID:{pub_acc.id}, UUID:{pub_uuid})")

                try:
                    # If an interrupt occurs during following processing, we want it to complete what has been started
                    proc_ftp_killer.allow_protected_exit("_create_unrouted_notification_from_ftp_deposit")
                    num_processed += 1
                    # Process a directory or zip file containing a single notification
                    _create_unrouted_notification_from_ftp_deposit(this_dir, pub_acc, pub_test)
                    num_ok += 1     # Increment OK count if preceding function does NOT raise exception
                    # Remove all files that have been processed.
                    shutil.rmtree(this_dir)

                except Exception as e:
                    pub_test.log(ERROR, f"Failed to create unrouted notification {this_dir} for Acc: '{pub_acc.org_name}' (ID:{pub_acc.id}, UUID:{pub_uuid}) - {repr(e)}",
                                 save=False)
                    # Move problem files to error files store
                    _move_files_to_error_dir(pub_uuid, this_dir)
                    if isinstance(e, DAOException) and e.abend:
                        raise e
                finally:
                    proc_ftp_killer.cancel_protected_exit()
    except Exception as e:
        app.logger.critical(
            f"Problem processing FTP directories. Last directory processed was '{this_dir}' - {repr(e)}")
    except ProcessKilled:
        pass
    finally:
        metrics.log_and_save(log_msg=f". Processed {{}} file{{}} ({num_ok} successfully)",
                             count=num_processed,
                             extra={"num_ok": num_ok})
        job_result = JobResult(count=num_processed)
        if proc_ftp_killer.killed:
            job_result.job_flag = JobResult.KILL_SCHEDULE
        proc_ftp_killer.restore_behaviour()
    return job_result


def _after_unrouted_run():
    after_run_action(app.logger,
                     app.config.get("ROUTE_ACTION_AFTER_RUN"),
                     "After Routing",
                     [UnroutedNotification, HarvestedNotification]
                     )


def _process_unrouted(harvested):
    """
    Processes unrouted notifications - attempt to match them to repositories.

    There are 2 sources:

    EITHER
    Publisher unrouted notifications in the `notification` table that have been created via any of the following means:
        * via FTP (1.move_ftp_from_jail_to_temp --> 2.processftp)
        * via API
        * via SWORD2
    OR
    Harvested unrouted notifications that have been created by the Harvester process - these reside in
    `harvested_unrouted` table

    Checks the unrouted-notification table and process any notifications found there: routing them to repositories where
    the matching criteria are satisfied.

    The result of this process is that notifications which match at least one repository will become designated as
    "routed" notifications, and unmatched notifications are deleted from the database.

    :param harvested: Boolean - True: process harvested notifications; False: process publisher submitted notifications
    :return: JobResult object with count set to `num_routed` and `func_return` set to (note_count, num_routed)
    """
    # Once the job has run, there may be a required action (set via config)
    job_result = JobResult(after_run_action_fn=_after_unrouted_run)

    raise_exc = None
    if harvested:
        unrouted_type = "harvested"
        unrouted_class = HarvestedNotification
        delete_pub_unrouted = False  # NOTE harvested unrouted are deleted via different mechanism
    else:
        unrouted_type = "publisher"
        unrouted_class = UnroutedNotification
        delete_pub_unrouted = app.config.get("DELETE_UNROUTED", False)

    metrics = MetricsRecord(
        server=app.config.get("SERVER_ID", "Dev"), proc_name=f"Route-{unrouted_type.title()}", measure="note"
    )
    if trace_memory:
        snap_num = mem_trace.snapshot()  # MMM
        print(f"\n\n====MMM====>>>> Start _process_unrouted {unrouted_type} Snapshot: {snap_num} =====\n")  # MMM

    unrouted_ids_no_pkgs = []  # List of IDs of notifications without a stored package which were not routed
    unrouted_ids_with_pkgs = []  # List of IDs of notifications which have a stored package which were not routed
    note_count = 0
    num_routed = 0
    note_id = None
    
    proc_unrouted_killer = StandardGracefulKiller(app.logger,
                                                  f"Process {'Harvested ' if harvested else ''}Unrouted")
    proc_unrouted_killer.allow_protected_exit("_process_unrouted")
    try:
        if app.config.get("LOG_DEBUG"):
            app.logger.debug(f"_process_unrouted: Check for {unrouted_type} unrouted notifications")

        # This data is retrieved before the unrouted-scroller processing loop for processing efficiency; however, it
        # means that any changes to account status Live/Test or On/Off that occur during the processing loop will not
        # be acted upon. The chance of such changes is low, and they would in any event be applied in subsequent calls
        # to _process_unrouted().
        test_publisher_ids = AccOrg.get_test_publisher_ids()
        test_harvester_ids = HarvesterWebserviceModel.get_test_harvester_ids()
        # Data for ALL active repo accounts is retrieved here before scrolling thru unrouted notifications
        # it occupies a lot of memory (some matching params have many ORCIDs & grant nums), but previously
        # when each Repo Ac & Matching param was being retrieved from database when needed (within `route` & `match`
        # functions) this was causing severe memory leak problem that resulted in RAM usage increasing from
        # few to many % during a single execution of loop.
        active_repo_tuples_list = AccOrg.get_active_repo_routing_data_tuples()

        # returns a list of unrouted notification from the last three up to four months
        unrouted_scroller = unrouted_class.unrouted_scroller_obj()
        with unrouted_scroller:
            for notification in unrouted_scroller:
                if proc_unrouted_killer.killed:
                    break
                routed_bool = False
                try:
                    note_id = notification.id
                    note_count += 1
                    # Attempt to route the notification to appropriate repositories (i.e. where the repository's matching
                    # criteria are satisfied). A routed notification is one that has been matched to at least 1 repository.
                    routed_bool = route(notification, test_publisher_ids, test_harvester_ids, active_repo_tuples_list)
                except Exception as e:
                    app.logger.error(

                        f"Failed to route {unrouted_type} unrouted: {note_id}, adding to unrouted list, continuing - {repr(e)}")
                    if isinstance(e, DAOException) and e.abend:
                        raise e
                finally:
                    if routed_bool:
                        num_routed += 1
                    elif delete_pub_unrouted:
                        if notification.packaging_format is None:  # Unrouted notification has NO package content
                            unrouted_ids_no_pkgs.append(note_id)
                        else:
                            unrouted_ids_with_pkgs.append(note_id)
    except Exception as e:
        try:
            unrouted_count = unrouted_class.count()
        except Exception:
            unrouted_count = "???"
        app.logger.critical(f"Process '{unrouted_type} unrouted' failed after processing {note_count} of {unrouted_count} notifications - {repr(e)}")
        # Raise e if Exception is NOT a DAOException or if it is a DAOException AND e.abend is True
        if not isinstance(e, DAOException) or e.abend:
            raise_exc = e

    try:
        if harvested:
            if note_id:
                # if last notification processed equals last notification in table, then can delete all entries
                # by truncating table (v. efficient)
                if note_id == HarvestedNotification.max_id():
                    HarvestedNotification.truncate_table()
                else:
                    HarvestedNotification.bulk_delete_less_than_equal_id(note_id)
        elif unrouted_ids_no_pkgs or unrouted_ids_with_pkgs:
            # If any notifications were not routed (and their deletion is required)
            # Use `del_upto_max` notification deletion strategy because we never want to revisit any of the unrouted
            # notifications, and IDs are assigned sequentially
            JPER.delete_unrouted_notifications_and_files(unrouted_ids_no_pkgs, unrouted_ids_with_pkgs,
                                                         del_upto_max=True)
    except Exception as e:
        snippet = "\n*** Manual table truncation may be needed to avoid sending duplicates ***\n" if harvested else ""
        app.logger.critical(
            f"_process_unrouted: Problem deleting harvested {unrouted_type} notifications{snippet} - {repr(e)}\n"
        )
        # If an Earlier serious error DID NOT occur then raise this one (we don't want to overwrite original exception)
        if not raise_exc:
            raise_exc = e
    finally:
        fatal_msg = " until FATAL exception occurred" if raise_exc else ""
        extra = {
            "num_routed": num_routed
        }
        if fatal_msg:
            extra["error"] = truncate_string(repr(raise_exc), max_len=1000)
        metrics.log_and_save(
            log_msg=f". Processed {{}} {unrouted_type} unrouted notification{{}} ({num_routed} were routed){fatal_msg}",
            count=note_count,
            extra=extra
        )

    # Earlier serious error occured, so raise that here
    if raise_exc:
        job_result.exception = raise_exc

    if trace_memory:
        snap_num = mem_trace.snapshot()  # MMM
        print(f"\n\n====MMM====<<<< Finish _process_unrouted {unrouted_type} Snapshot: {snap_num} =====\n")  # MMM
        mem_trace.compare_snapshots(unrouted_type, 0, snap_num - 1)  # MMM
        if snap_num > 2:  # MMM
            mem_trace.compare_snapshots(unrouted_type, snap_num - 2, snap_num - 1)  # MMM
        mem_trace.print_last_snapshot_trace(unrouted_type)  # MMM
        print(f"\n====MMM=== End diagnostic output ====\n", flush=True)  # MMM

    job_result.count = num_routed
    job_result.func_return = (note_count, num_routed)
    if proc_unrouted_killer.killed:
        job_result.job_flag = JobResult.KILL_SCHEDULE
    proc_unrouted_killer.restore_behaviour()
    return job_result


def check_unrouted():
    """
    Processes unrouted notifications that have been created via any of the following means:
        * via FTP (1.move_ftp_from_jail_to_temp --> 2.processftp)
        * via API
        * via SWORD2

    Checks the `notification` data table and processes any unrouted notifications found there: routing them to
    repositories where the matching criteria are satisfied.

    The result of this process is that notifications which match at least one repository will become designated as
    "routed" notifications, and unmatched notifications are deleted from the database.

    :return: JobResult object with count set to `num_routed` and `func_return` set to (note_count, num_routed)
    """
    return _process_unrouted(False)  # False: NOT processing harvested unrouted


def check_harvested_unrouted():
    """
    Processes unrouted notifications that have been created by Harvester.

    Checks the `harvested_unrouted` data table and process any notifications found there: routing them to repositories
    where the matching criteria are satisfied.

    The result is that notifications which match at least one repository will become designated as "routed"
    notifications and are saved in notification table, & unmatched notifications are deleted from the database.

    :return: JobResult object with count set to `num_routed` and `func_return` set to (note_count, num_routed)
    """
    return _process_unrouted(True)  # True: Processing harvested unrouted


def monthly_jobs():
    """
    Run jobs which only need to be run once per month:
        - Monthly reporting

    Refers to a file (monthtracker.cfg) which stores 'month last run' to determine whether a new month has occurred
    or not.
    """
    job_result = JobResult()
    try:
        # Obtain the last run month from file, default to '' if file not found
        reportsdir = app.config.get('REPORTSDIR', '/var/pubrouter/reports')
        monthtracker = reportsdir + '/monthtracker.cfg'
        try:
            with open(monthtracker, 'r') as lm:
                last_month = lm.read().strip('\n')
        except:
            # May have failed due to missing directory, in which case create it
            if not os.path.exists(reportsdir):
                os.makedirs(reportsdir)
            last_month = ''

        # Get the current month
        text_month = datetime.now(tz=timezone.utc).strftime("%b")

        # If a new month, then run the monthly jobs
        if last_month != text_month:
            monthly_killer = StandardGracefulKiller(app.logger, "Monthly jobs")
            monthly_killer.allow_protected_exit("_create_monthly_statistics_records")
            total_recs = 0
            metrics = MetricsRecord(server=app.config.get("SERVER_ID", "Dev"), proc_name="Monthly", measure="rec")
            try:
                app.logger.info('Scheduler monthly_jobs: New month - running monthly jobs')

                # Generate monthly statistics
                total_recs = _create_monthly_statistics_records()

                if app.config.get("SCHEDULE_MONTHLY_REPORTING"):
                    monthly_killer.allow_protected_exit("_monthly_reporting")
                    _monthly_reporting(reportsdir)

                # UPDATE monthtracker FILE
                with open(monthtracker, 'w') as f:
                    f.write(text_month)
            finally:
                metrics.log_and_save(log_msg=". Created {} statistics record{}", count=total_recs)
                if monthly_killer.killed:
                    job_result.job_flag = JobResult.KILL_SCHEDULE
                monthly_killer.restore_behaviour()
    except Exception as e:
        app.logger.critical(f"Failed monthly jobs - {repr(e)}", exc_info=True, extra={"subject": "Monthly jobs failure"})

    return job_result


def _database_reset():
    """
    Perform a reset / tidy-up of database.
    """
    database_reset(app.logger)


def _shutdown():
    """
    Terminate the application - causing all scheduler jobs to be PURGED & all database connections be closed.
    """
    return JobResult(job_flag=JobResult.PURGE_SCHEDULE)


# maps process strings to their respective functions
master_process_map = {
    "move_ftp": move_ftp_from_jail_to_temp,
    "process_ftp": processftp,
    "route": check_unrouted,
    "route_harv": check_harvested_unrouted,
    "delete_old": delete_old_data,
    "delete_files": delete_old_files,
    "monthly_jobs": monthly_jobs,
    "adhoc_report": adhoc_report,         # Takes at least 2 params: report_type, email_to
    "database_reset": _database_reset,
    "shutdown": _shutdown,
}


@app_decorator
def run(jobs_list=None):
    """
    Schedule the required processes: moveftp, processftp, check_unrouted, monthly_reporting, delete_old_routed etc.

    The actual processes that will be scheduled depends on jobs_list.

    :param jobs_list: List of Strings - ["job_keywords", ...,] corresponding to keys in master_process_map
    :return: Doesn't return - loops forever
    """
    job_list = jobs_list or app.config.get("SCHEDULER_JOBS") or []
    if "sword_out" in job_list:
        from router.jper_sword_out.deposit import Deposit
        add_extra_config(app,
                         ["router.jper_sword_out.config.base", "router.jper_sword_out.config.{env}"],
                         add_local_config=True)
        print_config_vals(app, f"\nAdditional configuration added for SWORD OUT\n\n")

        def _after_sword_run():
            after_run_action(app.logger,
                             app.config.get("SWORD_ACTION_AFTER_RUN"),
                             "After running SWORD-out",
                             Deposit.classes_for_cursor_close())

        def sword_out():
            Deposit.init_cls()

            # Once the job has run, there may be a required action (set via config)
            job_result = JobResult(after_run_action_fn=_after_sword_run)

            metrics = MetricsRecord(server=app.config.get("SERVER_ID", "Dev"), proc_name="SWORD-out", measure="deposit")
            try:
                Deposit.send_notes_to_sword_acs()
            except Exception as e:
                app.logger.critical(f"SWORD-Out run failed: {repr(e)}")
                job_result.exception = e
            finally:
                job_result.count = Deposit.total_deposits
                metrics.log_and_save(log_msg=". Made {} deposit{}", count=Deposit.total_deposits)
                Deposit.graceful_killer.restore_behaviour()
            return job_result

        master_process_map["sword_out"] = sword_out

    # Change default log file path
    app.config["LOGFILE"] = app.config["SCHEDULER_LOGFILE"]

    initialise()

    app.logger.info("Scheduler - running --------------------------------")
    try:
        if trace_memory:
            mem_trace.start(10)  # MMM
        # Build process map using jobs_list (or SCHEDULER_JOBS configuration value)
        process_map = construct_process_map(master_process_map, job_list)
        schedule = Schedule(app.config.get("SERVER_ID", "Dev"),
                            "Scheduler",
                            app.config.get("SCHEDULER_SPEC", []),
                            app.config.get("SCHEDULER_CONFLICTS", {}),
                            process_map,
                            sleep_secs=app.config.get("SCHEDULER_SLEEP"),
                            logger=app.logger,
                            new_day_reload=False    # Not needed as application is shutdown daily (then automatically restarted)
                            )
        end_flag = schedule.run_schedule()
        if end_flag == JobResult.PURGE_SCHEDULE:
            schedule.purge_all_jobs()
        else:
            schedule.purge_jobs_for_server_prog()
        database_reset(app.logger)
    # except SystemExit:      # sys.exit() called somewhere
    #     pass
    except (ValueError, NoJobsScheduled) as e:
        msg = f"**** TERMINATING with exception: {repr(e)}"
        app.logger.critical(msg, extra={"subject": "Scheduler problem"})
        print("\n", msg)
        exit(1)
    except Exception as e:
        schedule.purge_jobs_for_server_prog()
        DAO.abnormal_exit(e, "Scheduler ")


## ORIGINALLY scheduler was designed to optionally be run as a thread kicked off by jper process - but the process
## architecture was changed.  This is retained in unlikely event this might be wanted in future.
# def go():
#     from threading import Thread
#
#     thread = Thread(target=run)
#     thread.daemon = True   # Causes the thread (daemon) process to terminate when the parent process terminates
#     thread.start()


if __name__ == "__main__":
    print("Starting scheduler...")
    # Program may OPTIONALLY be called with a list of job keywords as commandline arguments - for example:
    #   python -m router.jper.scheduler monthly_jobs database_reset move_ftp process_ftp
    # If no args are passed, then ALL jobs may be executed (as specified in SCHEDULER_SPEC)
    run(argv[1:])

