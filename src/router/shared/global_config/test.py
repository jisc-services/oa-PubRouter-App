"""
Test environment configuration file for the JPER application

On deployment, desired configuration can be overridden using a local ~/.pubrouter/global.cfg file
"""
LOGLEVEL = 'DEBUG'
# LOGLEVEL = 'INFO'

# PUBLIC VERSION: obfuscate MYSQL_HOST & MYSQL_PWD & TEST_DB_ADMIN_PWD values
MYSQL_HOST = "XXXX-XXXX-pubrouter.ZZZZ.eu-west-1.rds.amazonaws.com"    # Aurora MySQL test instance
MYSQL_PWD = "XXXXYYYYXXXXYYYY"              # Password for MYSQL_USER "jper_user"
TEST_DB_ADMIN_PWD = "_test#db#admin%1234%pwd_"      # Password of TEST_DB_ADMIN_USER User: "test_admin"

SERVER_NAME = 'XXXX.jisc.ac.uk'
PREFERRED_URL_SCHEME = 'https'
SFTP_ADDRESS = f'sftp.{SERVER_NAME}'
BASE_URL = f'{PREFERRED_URL_SCHEME}://{SERVER_NAME}/'
JPER_BASE_URL = f'{BASE_URL}api/v4'
API_URL = f'{JPER_BASE_URL}/notification'
API_NOTE_URL_TEMPLATE = f'{BASE_URL}api/v{{}}/notification/{{}}'
SWORD_ADDRESS = f'{BASE_URL}sword2'

SCHEDULER_SPEC = [
    # (Label, Start-time, Interval, End-time, Process-name, Priority, Triggers)
    # "Label (unique)", "Start-time" (String "HH:MM"), Interval (Integer minutes OR String like '10s', '20m' or '3h'), "End-time" (String "HH:MM"), "Process-name" (String), Priority (Integer 1 to 4 - V.High to Low), Triggers (String or List of Strings)
    # In no Start-time then job needs to be triggered to run
    # If there is no Interval then job is assumed to be a one off event (though can be triggered multiple times)

    ## IOP tend to deposit from midnight. Usually takes 2.5 - 3 hours to complete.

    # IMPORTANT: The ES server used by 'harvest' is STARTED at Midnight and STOPPED at 02:30 a.m. each night.
    (None, "08:05", None, None, "delete_files", 1, None),
    (None, "08:10", None, None, "delete_old", 1, None),
    (None, "08:15", None, None, "monthly_jobs", 1, None),  # Reporting
    (None, "08:20", None, None, "harvest", 2, "RH1"),
    ("RH1", "09:00", None, None, "route_harv", 2, ["SO2", "MF2-always"]),  # Route following harvesting

    ("MF2", "09:10", 20, "18:45", "move_ftp", None, "PF2"),
    ("PF2", None, None, "18:45", "process_ftp", None, "RO2"),
    ("RO2", "09:20", 20, "18:45", "route", None, "SO2"),
    ("SO2", "09:25", 20, "18:45", "sword_out", None, None),
    ("REP", None, None, "18:45", "adhoc_report", 2, None),

    (None, "18:55", None, None, "shutdown", 1, None),
]
