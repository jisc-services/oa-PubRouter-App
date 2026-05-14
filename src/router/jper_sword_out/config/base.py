"""
Main configuration file for the JPER-SWORD-OUT application

On deployment, configuration can be overridden by using a local ~/.pubrouter/sword-out.cfg file
"""
import os
from octopus.lib.paths import get_real_path

LOGFILE = '/var/log/pubrouter/sword-out.log'

TEST_DB_NAME = "test_sword_out"  # Name of test database

#############################################
# Re-try/back-off settings
# from the http layer
# specific to this app

# Minimum time (seconds) to leave between repeat attempts to deposit, in the event that there was a deposit error
# 3600 secs ==> 1 hour
DEPOSIT_RETRY_DELAY = 3600

# Maximum number of times to attempt deposit before giving up and turning off repository sword submission
# for a given account
DEPOSIT_RETRY_LIMIT = 2

###############################################
# ** Other app-specific settings

# Earliest date for listing a repository's notifications
DEFAULT_SINCE_DATE = "1970-01-01T00:00:00Z"

# Time before SWORD client returns an error if the recipient does not respond (600 ==> 10 mins)
# Note that some Eprints deposits for articles with several thousand authors (have seen >5000 !) take a long time
SWORD_TIMEOUT_IN_SECONDS = 600

# Determine action to take after SWORD run executes.  Used to mitigate memory leak
# Options: None / 'exit' (exit process) / 'close_conn' (close ALL db connections) / 'close_curs' (close ALL cursors) / 'close_class_curs' (close cursors for list of Classes)
SWORD_ACTION_AFTER_RUN = None
TEMPLATE_PATH = get_real_path(__file__, "..", "templates")

# Standard local config file
LOCAL_CONFIG = os.path.expanduser("~/.pubrouter/sword-out.cfg")
