"""
Contains configuration that is used by ALL Router services/components (to avoid repeating in module configs).

On deployment, desired configuration can be overridden using a local ~/.pubrouter/global.cfg file

NB. This file contains DEVELOPMENT values or Linux values
"""
import os

# LOGLEVEL = 'DEBUG'

###############################
# MySQL
####
MYSQL_TIMEZONE = "+00:00"  # causes MySQL to return stored timestamps as UTC values
MYSQL_POOL_SIZE = None     # Not using connection pool (as found that caused MySQL max connections to be exceeded)
# MYSQL_READ_POOL_SIZE = None   # Not using connection pools
# MYSQL_WRITE_POOL_SIZE = None  # Not using connection pools
MYSQLX_MULTI_POOL = False       # Use a single connection pool (requires larger Pool size if pools are used)
MYSQLX_CONN_PER_CLASS = False   # True: Create up to 2 separate connections (transaction & read-only) per PID per Class - leads to more connections
                                # False: Create 2 separate (transaction & read-only) connections for use by ALL classes per PID
                                # PID: Process ID.  See /octopus/modules/mysql/dao.py for more info.
MYSQLX_FATAL_ERR_DICT = {"max": 3, "secs_period": 1800}  # Max number of grave errors allowed within period of X seconds
                                # If this limit is exceeded then the Abnormal-End (ABEND) flag is set in DAOException
                                # objects which can be used to trigger program termination - i.e. exit(1)
MYSQLX_FETCHMANY_SIZE = 10      # DAO Scroller: the default number of records to retrieve from database in each fetch

MYSQL_DB = "jper"
MYSQL_USER = "jper_user"
# MYSQL_HOST = "..."    DEFINE in each environment config file
# MYSQL_PWD = "..."     DITTO

TEST_DB_NAME = "test_app"  # Name of test database

###############################
# Important FLASK config overrides
####
# Enable user accounts
ACCOUNT_ENABLE = True

# Session management secret key
SECRET_KEY = "[t34*2<999888999~gK)u"

# Cache settings
# Variable names can be found at http://pythonhosted.org/Flask-Cache/#configuring-flask-cache
CACHE_TYPE = "filesystem"
CACHE_DIR = "/tmp/jper-cache"


###############################
# API related config
####
API_VERSION = "4"
OLD_API_VERSION = "3"
API_URL_PREFIX = f"/api/v{API_VERSION}"
OLD_API_URL_PREFIX = f"/api/v{OLD_API_VERSION}"
JPER_API_KEY = ""

###############################
# PUBLIC FACING Server name and URL scheme variables so url_for creates correct URLs
## DEFINE in each Environment config file
# SERVER_NAME = '...'
# PREFERRED_URL_SCHEME = '...'
# SFTP_ADDRESS = '...'
# BASE_URL = '...'
# # We DON'T need an "OLD" version of JPER_BASE_URL as only used by src.router.shared.client - which needs latest version only
# JPER_BASE_URL = '...'
# API_URL = '...'
# API_NOTE_URL_TEMPLATE = '...'
# SWORD_ADDRESS = '...'

################################
# STORE_TYPE ("temp"|"local"|"remote") - The PREFERRED way of specifying which store class StoreFactory.get() returns.
STORE_TYPE = None

# Class for temporary local filestore
STORE_TMP_IMPL = "octopus.modules.store.store.TempStore"

# Class for main filestore
# ***IMPORTANT*** STORE_IMPL will be ignored if STORE_TYPE is set in config
# STORE_IMPL = "octopus.modules.store.store.StoreRemote"      # Access store via Store API (if store is on remote server)
STORE_IMPL = "octopus.modules.store.store.StoreLocal"     # Use this to use local main store instead of web api store

## The following are Linux server values
# Web api Store endpoint
REMOTE_STORE_URL = 'http://store/'
# Path to main file store
STORE_MAIN_DIR = '/Incoming/store'
# Path to local directory for temp filestore
STORE_TMP_DIR = '/var/pubrouter/local_store/tmp'

SHELL_SCRIPT_DIR = '~/.pubrouter/sh'      # Location of shell scripts

################################
# Open License keywords - list contains "unique" substrings which are used to establish if a license URL is Open or not.
OPEN_LICENCE_KEYWORD_LIST = ["creativecommons", "authorservices.wiley.com/author-resources/Journal-Authors/licensing/self-archiving.html", "doi.org/10.1002/self_archiving_license_1.0", "www.intellectbooks.com/self-archiving#accepted-manuscript-post-embargo", "www.nationalarchives.gov.uk/doc/open-government-licence"]

################################
### Values required for Email connector (Linux default) ###
# SMTP server settings:
#   use_tls - True if server requires a secure connection.
#   requires_auth - Requires username/password authentication to use the server.
# Office365 settings if someone wanted to do local testing
# MAIL_SMTP_SERVER = {"host": "smtp.office365.com", "port": 587, "requires_auth": True, "use_tls": True}
MAIL_SMTP_SERVER = {"host": "localhost", "port": 25, "use_tls": True, "requires_auth": False}
# Whether or not to mock the email server
MAIL_MOCKED = False


################################
## The following are DEVELOPMENT values
SCHEDULER_SLEEP = 5         # Number of seconds to sleep between schedule process checks

# Dict that prevents key processes from running in parallel (simultaneously) with other processes
SCHEDULER_CONFLICTS = {
    # 'key-function-name': ['list-of-functions-that-if-running-delay-execution-of-key-function', ...]
    "route_harv": ["harvest"],
    "process_ftp": ["route", "route_harv"],
    "route": ["process_ftp", "route_harv", "adhoc_report"],
    "sword_out": ["route", "route_harv", "adhoc_report"],
    "adhoc_report": ["route", "sword_out", "route_harv"]
}

# SCHEDULER_SPEC = [
#     # (Label, Start-time, Interval, End-time, Process-name, Priority, Triggers)
#     # "Label (unique)", "Start-time" (String "HH:MM"), Interval (Integer minutes OR String like '10s', '20m' or '3h'), "End-time" (String "HH:MM"), "Process-name" (String), Priority (Integer 1 to 4 - V.High to Low), Triggers (String or List of Strings)
#     # In no Start-time then job needs to be triggered to run
#     # If there is no Interval then job is assumed to be a one off event (though can be triggered multiple times)
#
#     (None, "07:15", None, None, "harvest", 2, "RH1"),
#     ("RH1", "07:45", None, None, "route_harv", 2, ["SO2", "MF2-always"]),  # Route following harvesting
#     ("SO1", None, None, "03:00", "sword_out", None, None),
#     ("MF1", "01:30", 30, "03:00", "move_ftp", None, "PF1"),
#     ("PF1", None, None, "03:00", "process_ftp", None, "RO1"),
#     ("RO1", "02:00", 30, "03:00", "route", None, "SO1"),  # This may route a lot of IOP stuff
#     (None, "03:55", None, None, "delete_files", 1, None),
#     (None, "04:04", None, None, "delete_old", 1, None),
#     (None, "04:12", None, None, "monthly_jobs", 1, None),  # Reporting
#     (None, "04:25", None, None, "database_reset", 1, None),       # Daily reset (close database connections)
#
#     ("MF2", "08:00", 12, "21:59", "move_ftp", None, "PF2"),
#     ("PF2", None, None, "21:59", "process_ftp", None, "RO2"),
#     ("RO2", "08:06", 12, "21:59", "route", None, "SO2"),
#     ("SO2", "08:09", 12, "21:59", "sword_out", None, None),
#     ("REP", None, None, "21:59", "adhoc_report", 2, None)   # Ad hoc report job is always triggered from GUI
# ]


ID_TYPE_TO_URI = {
    # ID Type: ("base domain", first-segment)
    "doi": ("https://doi.org/", None),
    "isni": ("https://isni.org/isni/", None),
    "ror": ("https://ror.org/", None),
    # Crossref & FundRef are equivalent - both are converted to DOI, with first segment "10.13039/"
    "crossref": ("https://doi.org/", "10.13039/"),
    "fundref": ("https://doi.org/", "10.13039/")
}

################################
# On servers: /home/jenkins/.pubrouter/global.cfg
LOCAL_CONFIG = os.path.expanduser("~/.pubrouter/global.cfg")

