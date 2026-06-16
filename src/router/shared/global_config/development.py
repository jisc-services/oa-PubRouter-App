"""
Development environment configuration file for the JPER application

On deployment, desired configuration can be overridden using a local ~/.pubrouter/global.cfg file
"""
LOGLEVEL = "DEBUG"

## The following are Development values
MYSQL_HOST = "localhost"
MYSQL_PWD = "Admin_Pass1"   # Password for MYSQL_USER "jper_user"
MYSQL_DB = "jper_live"
# MYSQL_USER = "test_admin"
# MYSQL_PWD = "ABCabcXYZxyz"
# MYSQL_DB = "test"
# PUBLIC VERSION: obfuscate password
TEST_DB_ADMIN_PWD = "_test#db#admin%1234%pwd_"      # Password of TEST_DB_ADMIN_USER User: "test_admin"

SERVER_NAME = 'localhost:5998'
PREFERRED_URL_SCHEME = 'http'
SFTP_ADDRESS = f'sftp.{SERVER_NAME}'
BASE_URL = f'{PREFERRED_URL_SCHEME}://{SERVER_NAME}/'
# We DON'T need an "OLD" version of JPER_BASE_URL as only used by src.router.shared.client - which needs latest version only
JPER_BASE_URL = f'{BASE_URL}api/v4'
API_URL = f'{JPER_BASE_URL}/notification'
API_NOTE_URL_TEMPLATE = f'{BASE_URL}api/v{{}}/notification/{{}}'     # Placeholders for Version-num & ID
SWORD_IN_SERVER_NAME = 'localhost:5990'
SWORD_ADDRESS = f'{PREFERRED_URL_SCHEME}://{SWORD_IN_SERVER_NAME}/sword2'

REMOTE_STORE_URL = "http://localhost:5999"
# Path to local directory for local filestore - mainly used for testing - relative to this file
STORE_MAIN_DIR = '/Incoming/app_local_store/live'
# Path to local directory for temp filestore - relative to this file
STORE_TMP_DIR = '/Incoming/app_local_store/tmp'

MAIL_SMTP_SERVER = {"host": "smtp.office365.com", "port": 587, "requires_auth": True, "use_tls": True}
#MAIL_SMTP_SERVER = {"host": "localhost", "port": 25, "use_tls": True, "requires_auth": False}
# MAIL_MOCKED = True    # Use mock server - emails not visible
MAIL_MOCKED = "print"   # Use mock server - emails are printed to StdOut

SCHEDULER_SPEC = [
    # (Label, Start-time, Interval, End-time, Process-name, Priority, Triggers)
    # "Label (unique)", "Start-time" (String "HH:MM"), Interval (Integer minutes OR String like '10s', '20m' or '3h'), "End-time" (String "HH:MM"), "Process-name" (String), Priority (Integer 1 to 4 - V.High to Low), Triggers (String or List of Strings)
    # In no Start-time then job needs to be triggered to run
    # If there is no Interval then job is assumed to be a one off event (though can be triggered multiple times)

    (None, "07:15", None, None, "harvest", 2, "RH1"),
    ("RH1", "07:45", None, None, "route_harv", 2, ["SO2", "MF2-always"]),  # Route following harvesting
    # ("SO1", None, None, "03:00", "sword_out", None, None),
    # ("MF1", "01:30", 30, "03:00", "move_ftp", None, "PF1"),
    # ("PF1", None, None, "03:00", "process_ftp", None, "RO1"),
    # ("RO1", "02:00", 30, "03:00", "route", None, "SO1"),  # This may route a lot of IOP stuff
    # (None, "03:55", None, None, "delete_files", 1, None),
    # (None, "04:04", None, None, "delete_old", 1, None),
    # (None, "04:12", None, None, "monthly_jobs", 1, None),  # Reporting
    # (None, "04:25", None, None, "database_reset", 1, None),       # Daily reset (close database connections)

    ("MF2", "08:00", 12, "21:59", "move_ftp", None, "PF2"),
    ("PF2", None, None, "21:59", "process_ftp", None, "RO2"),
    ("RO2", "08:06", 12, "21:59", "route", None, "SO2"),
    ("SO2", "08:09", 12, "21:59", "sword_out", None, None),
    ("REP", None, None, "21:59", "adhoc_report", 2, None)   # Ad hoc report job is always triggered from GUI
]
