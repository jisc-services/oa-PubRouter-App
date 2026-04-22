"""
Main configuration file for the Router SWORD-IN application

On deployment, configuration can be overridden by using a local ~/.pubrouter/sword-in.cfg file
"""
import os
from octopus.lib.paths import get_real_path
from zipfile import ZIP_STORED, ZIP_DEFLATED

LOGFILE = '/var/log/pubrouter/sword-in.log'

TEST_DB_NAME = "test_sword_in"  # Name of test database

# Webserver port
PORT = 5990
# Support for SSL requests
SSL = False
# Webserver threaded mode
THREADED = True

# SWORD CONFIG - specifies the model library code to use
AUTH_IMPL = "router.jper_sword_in.models.sword.JPERSwordAuth"
REPO_IMPL = "router.jper_sword_in.models.sword.JPERRepository"
REPO_ARGUMENTS = []


# Whether SWORD model code should delete SWORD2 deposit after successfully converting it into Router Notification
# If False, then deposit will remain in TempStore until a separate Scheduler nightly process deletes it after X days
# If True, then the Sword deposit is deleted from TempStore immediately after successfully converting to Notification
DELETE_AFTER_INGEST = False

SWORD_SERVER_TITLE = "Publications Router SWORD2 Server"
FEED_MAX_CONTAINERS = 50    # Maximnum number of containers to return for Feed
FEED_DESCRIPTION = f"The feed contains the last {FEED_MAX_CONTAINERS} deposits at most.  NOTE: completed deposits cannot be retrieved via SWORD2 as they have been converted into Router notifications."
IN_PROGRESS_DESCRIPTIONS = {
    True: "Deposit in progress.",
    False: "Deposit complete; Router notification generated."
}

# Zipfile compression type: ZIP_STORED: no compression, ZIP_DEFLATED: compress the file
# Used when REPACKAGING zip files
ZIP_COMPRESSION = ZIP_DEFLATED

###############################################
# ** Other app-specific settings

TEMPLATE_PATH = get_real_path(__file__, "..", "templates")

# Standard local config file
LOCAL_CONFIG = os.path.expanduser("~/.pubrouter/sword-in.cfg")
