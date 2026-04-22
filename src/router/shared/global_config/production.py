"""
Production environment configuration file for the JPER application

On deployment, desired configuration can be overridden using a local ~/.pubrouter/global.cfg file
"""
LOGLEVEL = 'INFO'

# PUBLIC VERSION: obfuscate details
MYSQL_HOST = "XXXX-XXXX-pubrouter.ZZZZ.eu-west-1.rds.amazonaws.com"    # Aurora MySQL Production instance
MYSQL_PWD = "XXXXYYYYXXXXYYYY"              # Password for MYSQL_USER "jper_user"
TEST_DB_ADMIN_PWD = "NOT-APPLICABLE"        # Testing never done in Production

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
    (None, "00:15", None, None, "harvest", 2, "RH1"),
    ("RH1", "01:00", None, None, "route_harv", 2, ["SO1", "MF1-always"]),  # Route following harvesting
    ("SO1", None, None, "03:03", "sword_out", None, None),
    ("MF1", "01:30", 20, "03:03", "move_ftp", None, "PF1"),
    ("PF1", None, None, "03:03", "process_ftp", None, "RO1"),
    ("RO1", "01:40", 20, "03:03", "route", None, "SO1"),  # This may route a lot of IOP stuff
    (None, "03:55", None, None, "delete_files", 1, None),
    (None, "04:04", None, None, "delete_old", 1, None),
    (None, "04:12", None, None, "monthly_jobs", 1, None),  # Reporting
    # "",  ("04:20", None, None, "database_reset"),       # Daily reset (close database connections)
    (None, "04:28", None, None, "shutdown", 1, None),  # Exit the application after closing database connections
    # (supervisord then automatically restarts it) - this to remedy any memory leaks

    # AWS window
    # ("", "04:30", None, None, "db_backup", None, None),       # Done by AWS Aurora MySQL - allow 30 mins
    # ("", "05:00", None, None, "db_maintenance", None, None),    # Weekly AWS Aurora MySQL maintenance window - allow 1 hour

    # CRIS vendor window - CRISs tend to harvest from 06:00-08:00

    (None, "08:00", 20, "23:59", "move_ftp", None, "PF2"),
    ("PF2", None, None, "23:59", "process_ftp", None, "RO2"),
    ("RO2", "08:10", 20, "23:59", "route", None, "SO2"),
    ("SO2", "08:15", 20, "23:59", "sword_out", None, None),
    ("REP", None, None, "23:59", "adhoc_report", 2, None)     # Ad hoc report job is always triggered from GUI
]
