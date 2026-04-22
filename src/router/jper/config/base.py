"""
Main configuration file for the JPER application

On deployment, configuration can be overridden by using a local ~/.pubrouter/jper.cfg file
"""
import platform
import os
from zipfile import ZIP_STORED, ZIP_DEFLATED
from datetime import timedelta
from octopus.lib.paths import get_real_path

TEST_DB_NAME = "test_jper"  # Name of test database

LOGFILE = '/var/log/pubrouter/jper.log'
# Log file so scheduler logs can be separated from JPER
SCHEDULER_LOGFILE = '/var/log/pubrouter/scheduler.log'
# Log file used for publisher testing output
PUB_TEST_LOG = '/var/log/pubrouter/publisher_testing.log'

# Defines which jobs the scheduler includes in process_map (None --> ALL jobs from master_process_map)
# May be overridden in jper.cfg if scheduler is run on >1 app server (see jenkins_deployment.sh)
SCHEDULER_JOBS=None

# Determine action to take after routing step `_process_unrouted()` executes.  Used to mitigate memory leak
# Options: None / 'exit' (exit process) / 'close_conn' (close ALL db connections) / 'close_curs' (close ALL cursors) /
# 'close_class_curs' (close cursors for list of Classes)
ROUTE_ACTION_AFTER_RUN = None


# Webserver port
PORT = 5998
# Support for SSL requests
SSL = False
# Webserver threaded mode
THREADED = True

###############################
# Enable OS FTP accounts for UNIX machines
UNIX_FTP_ACCOUNT_ENABLE = platform.system() == "Linux"

###############################
# GUI screen config
# Default page size for list requests
DEFAULT_LIST_PAGE_SIZE = 25
# Maximum page size
MAX_LIST_PAGE_SIZE = 100

PACKAGE_HANDLERS = {
    ## "http://router.jisc.ac.uk/packages/FilesAndJATS": "jper.packages.FilesAndJATS",
    "https://pubrouter.jisc.ac.uk/FilesAndJATS": "router.jper.packages.FilesAndJATS",
    "http://purl.org/net/sword/package/SimpleZip": "router.jper.packages.SimpleZip"
}

# various packaging options each repository type could have
# If there are more than one in the list, then the first one is the default
# Each item in a list is a tuple of (packaging URI, packaging description) to be used in creation of forms
REPOSITORY_PACKAGING_OPTIONS = {
    "": [("http://purl.org/net/sword/package/SimpleZip", "None")],     # Corresponds to XML_FORMAT_CHOICES of None
    "eprints": [("http://purl.org/net/sword/package/SimpleZip", "SimpleZip")],
    "eprints-rioxx": [("https://pubrouter.jisc.ac.uk/PDFUnpacked", "PDFUnpacked")],
    "eprints-rioxx-2": [("https://pubrouter.jisc.ac.uk/PDFUnpacked", "PDFUnpacked")],
    "dspace": [("http://purl.org/net/sword/package/SimpleZip", "SimpleZip")],
    "dspace-rioxx": [("http://purl.org/net/sword/package/SimpleZip", "SimpleZip")],
    "native": [("http://purl.org/net/sword/package/SimpleZip", "SimpleZip")]
}

# Base directory for publisher FTP jail directories. This is ASSUMED in ssh config and possibly in shell scripts, so
# DO NOT CHANGE it.
USERDIR = '/home/sftpusers'

# FTP_TMP_DIR: Temporary storage for article (zip) files requiring processing. Files are moved here from individual
# FTP Jail directories.  (Files are removed from this directory as they are processed).
FTP_TMP_DIR = "/Incoming/ftptmp"

# FTP_SAFETY_DIR: location for saving a copy of each FTP file received.
# It is needed for Atypon zip files, which are NOT moved to ftperrors directory if a file cannot be INITIALLY processed.
# Contents are deleted after X days by 'delete_old_ftp_files.sh' cron job (see deployment directory).
FTP_SAFETY_DIR = "/Incoming/tmparchive"
FTP_SAFETY_KEEP_DAYS = "7"  # Keep for 7 days before deleting

# FTP_ERROR_DIR: Location for storing problematic FTP zip file packages.
# Contents are deleted after X days by 'delete_old_ftp_files.sh' cron job (see deployment directory).
FTP_ERROR_DIR = "/Incoming/ftperrors"  # Location to move problem ftp packages to
FTP_ERROR_KEEP_DAYS = "28"  # Keep for 28 days before deleting

# If an Active (S)FTP connection exists, this defines how old a file must be before it can be moved. The value is the
# minimum number of seconds that must have elapsed since its last-modified-timestamp was (last) set.
# IMPORTANT: If this config value is absent or set to None, then NO files will be moved from an ftp directory of a
# a particular account while it has an Active FTP connection.
ACTIVE_FTP_MIN_SECS_SINCE_LAST_MODIFIED = 1800 # 30 minutes

# Minimum number of hours that an SFTP connection must exist for before it can be killed
# IMPORTANT - if set to 0 (zero) then the process will NOT be executed
SFTP_KILL_AFTER_X_HOURS = 4
SFTP_KILL_LOG = '/var/log/pubrouter/sftp_kill.log'


# If DELETE_UNROUTED is True, then UnroutedNotification database entries will be deleted after processing
# if they resulted in NO Notifications being sent to any Repository (see scheduler.py)
DELETE_UNROUTED = True

# Scheduler can also do necessary reporting jobs.
REPORTSDIR = "/var/pubrouter/reports"
# If SCHEDULE_MONTHLY_REPORTING is True, then in scheduler.py the monthly reporting job is run EACH DAY at '00:05' hours
SCHEDULE_MONTHLY_REPORTING = True

# Scheduler can also remove old data from database
SCHEDULE_DELETE_OLD_DATA = True     # Whether to delete old data
# Number of months worth of data to keep, any records older than that will be deleted
SCHEDULE_NOTIFICATION_KEEP_MONTHS = 3
# Dict determining which records will be deleted
SCHEDULED_DELETION_DICT = {
    # "table-name": ("Deletion-Query-Name", months-to-keep)
    # Deletion-query-name must correspond to an entry in __delete_cursor_dict__ of relevant class in
    # shared/mysql_dao.py file
    "notification": ("older_than", SCHEDULE_NOTIFICATION_KEEP_MONTHS),
    "content_log": ("older_than", SCHEDULE_NOTIFICATION_KEEP_MONTHS),
    "match_provenance": ("older_than", SCHEDULE_NOTIFICATION_KEEP_MONTHS),
    "pub_deposit": ("older_than", 12),
    "pub_test": ("older_than", 12),
    "sword_deposit": ("older_than", 12),
    "h_errors": ("older_than", 3),
    "h_history": ("older_than", 3),
    "acc_repo_match_params_archived": ("older_than", 24),   # recs are deleted after 24 months
    "acc_bulk_email": ("deleted_status", 12),   # recs are only deleted after 12 months if they also have status == "D"
    "acc_notes_emails": ("deleted_status", 12),   # recs are only deleted after 12 months if they also have status == "D"
    "cms_html": ("deleted_status", 3),   # recs with status of "D" or "S" are deleted after 3 months
    "metrics": ("older_than_count", 12)   # Keep all for 1 year, and non-zero count forever.
}



################################
# Maximum permitted deposited zip file size - 2.3 GB
MAX_ZIP_SIZE = 2469606196
# Large zip file size - 2 GB - files larger than this will have max compression applied when repackaging
LARGE_ZIP_SIZE = 2147483648

### Zip file compression options
# Zipfile compression type: ZIP_STORED: no compression, ZIP_DEFLATED: compress the file
ZIP_COMPRESSION = ZIP_DEFLATED
# Degree of compression (only applies if ZIP_COMPRESSION = ZIP_DEFLATED is set)
# NOTE - In zlib.py, def compressobj(), it says that the default compression is currently equivalent to 6.
# Higher values produce smaller files, but takes more resource & time
# Compression level: None = use default; 0 = No compression, 9 = Max compression.
ZIP_STD_COMPRESS_LEVEL = None
ZIP_XTRA_COMPRESS_LEVEL = 8

################################
# Configuration for when the app is operated in functional testing mode

# Start App in functional test mode - for TESTING ONLY
FUNCTIONAL_TEST_MODE = False

# URL to Router public documentation Github repo
DOCU_BASE_URL = 'https://github.com/jisc-services/Public-Documentation/tree/development/PublicationsRouter'
DOCU_API_URL = f"{DOCU_BASE_URL}/api/v4"


# Formatter for reports email subject.
# args in order:
#   Type of report ("institutions", "institutions_test" or "publishers")
#   Year of report ("2017")
#   Month of report ("08")
EMAIL_SUBJECT_REPORTS_FORMAT = "Publications Router report: monthly notifications {}-{}"
# Email address dict, should be written in the format
#     {
#         "email_address@address.com": [PUBLISHER_REPORT, HARVESTER_REPORT, ... ],
#         "email_address_two@address.com": [LIVE_INSTITUTION_REPORT, ... ]
#     }
OA_ROUTER_EMAIL = "XXXX.YYYY@YYYY.ac.uk"
REPORT_EMAIL_ADDRESSES = {
    OA_ROUTER_EMAIL: ["institutions_live", "institutions_test", "publisher", "harvester", "dup_submission"]
}
PUB_DOI_REPORT = "publisher_doi"

# YOUR-ORG emails accounts that are to receive reports of particular types
SUPPORT_EMAIL_ACS = [OA_ROUTER_EMAIL]
PUB_TEST_OK = True
PUB_TEST_ERROR = False
PUB_TEST_EMAIL_ADDR = {
    PUB_TEST_OK: SUPPORT_EMAIL_ACS,
    PUB_TEST_ERROR: SUPPORT_EMAIL_ACS,
}
CONTACT_CC = ["contact_test_cc@YOUR-ORG.ac.uk"]
CONTACT_BCC = SUPPORT_EMAIL_ACS

# Other report (e.g. Publisher DOI report) BCC list
REPORT_BCC = SUPPORT_EMAIL_ACS

TEMPLATE_PATH = get_real_path(__file__, "..", "templates")
STATIC_PATH = get_real_path(__file__, "..", "static")

# 2 commented out lines TO BE REMOVED in following release
# BLOG_URL = "https://scholarlycommunications.jiscinvolve.org/wp/category/publications-router/"
# OLD_BLOG_URL = ""
BLOG_URL = "https://research.jiscinvolve.org/wp/tag/publications-router/"
OLD_BLOG_URL = "https://web.archive.org/web/20240602215227/https:/scholarlycommunications.jiscinvolve.org/wp/"

# Indicates which of following services is running on a server: 'jper' / 'xweb' / 'xapi'.  This value is used by
# web_main.py to determine whether it should import the API view module & mount API endpoints.
WEB_API_TYPE = "jper"

# Required to address penetration test concern
SESSION_COOKIE_SECURE = True

FAILED_LOGIN_LIMIT = 10         # Number of failed login attempts after which a pause is enforced
FAILED_LOGIN_SLEEP_SECS = 20    # Initial number of seconds to pause, after repeated failed login attempts

REMEMBER_COOKIE_DURATION = timedelta(days=90)   # Login manager - remember-me cookie duration is 90 days, after which user will need to re-authenticate

# On servers: /home/jenkins/.pubrouter/jper.cfg
LOCAL_CONFIG = os.path.expanduser("~/.pubrouter/jper.cfg")

