#!/bin/bash
######################################################################
# Jenkins script for installing Router across ALL environments.  It does this using the version of Router
# that was (previously) built in the ${WORKSPACE} directory.  The `VERSION` file in that directory specifies
# the version number of the application being deployed.
#
# IMPORTANT: SWORD OUT process can be run either as separate Service "sword-out" OR as a scheduled Job "sword_out"
#            it should ONLY be executed as ONE or other of these. 
#
# Params:
#   1. Server Environment: one of [ production | staging | test ]
#   2. Build live flag: one of [ true | false ]
#   3. Service indicator string, containing any of following substrings, separated by bar (|), comma or space.
#         [ jper, xweb, xapi, harvester, scheduler-ftp, scheduler, sword-out, sword-in, store-app, no-store ]
#      EXAMPLES:  "jper|harvester|scheduler_ftp" or "sword-out|scheduler|store-app|sword-in"
#      IMPORTANT:
#         - "jper" runs the Web GUI & API app using gunicorn on App1 server only
#         - "xweb" runs the Web GUI app using gunicorn on (App1 server only)
#         - "xapi" runs the API app using gunicorn on (App2 server only)
#             If "jper" is specified, then "xweb" and "xapi" must NOT be; if "xweb" is specified (App1) then "xapi"
#             must be specified for App2.
#         - "sword-in" runs the SWORD2 server app using gunicorn on (App2 server only)
#         - "scheduler-ftp" - use if scheduler is being run on the FTP server
#         - "scheduler" - use if scheduler is being run on other server (will not be able to run jobs related to FTP)
#         - "no-store" means that NO store App is installed, which is appropriate if ALL other services are installed
#            on a single server (in this case the /Store directory will be accessed directly via file-system calls)
#         - "store-app" means that services are installed on more than 1 server, the store App must then be installed on
#            the server on which the /Store directory is located
#         - "sword-out" runs SWORD OUT as separate application service - DO NOT specify this if SWORD OUT is to be run
#            by scheduler ("sword_out" is specified in jobs string)  
#   4. Scheduler jobs string: contains '|' separated job keywords from set shown below OR none (empty). ONLY useful
#      if 'scheduler' service is specified in service indicator string (param #3)
#         [move_ftp, process_ftp, route, route_harv, sword_out, delete_old, monthly_jobs, database_reset, shutdown]
#       EXAMPLE: "move_ftp|process_ftp"
#      IMPORTANT: Do NOT specify "sword_out" job if "sword-out" is specified in Service indicator string.
#--------------------------------------
#   This script relies on Jenkins providing the following Environment Variables: NODE_NAME
#
# Author: Jisc
######################################################################
echo -e "\n---- Jenkins Deployment Script ----\n"

#### HANDLE PARAMETERS ####

# Server environment defaults to 'test' if no param passed
SERVER_ENV=${1:-test}
echo -e "* Server env: $SERVER_ENV."

# Build live defaults to 'false' if no param passed
BUILD_LIVE=${2:-false}
echo -e "* Build live: $BUILD_LIVE."

# Service version defaults to "jper|harvester|scheduler|sword-out|no-store" if not param passed
SERVICES="${3:-jper|harvester|scheduler-ftp|sword-out|no-store}"
echo -e "* Services: '$SERVICES'."

# Scheduler jobs defaults to empty string
SCHEDULER_JOBS="${4:-}"
echo -e "* Scheduler jobs: '$SCHEDULER_JOBS'."

#### BASIC VALIDATION ####

# Check that NOT attempting to run SWORD-OUT both as a separate App service & as a Scheduled job (on same server)
# NB. this check cannot identify error case where SWORD-OUT is being run on separate servers
if [[ $SERVICES = 'sword-out' ]] && [[ $SCHEDULER_JOBS = 'sword_out' ]] ; then
  echo -e "\n*** ERROR: You are attempting to run SWORD-OUT *both* as a separate app service and as a scheduled job."
  echo -e "\n*** You should either include 'sword-out' in SERVICES or 'sword_out' in SCHEDULER_JOBS (with 'scheduler' in SERVICES).\n\n"
  exit 1
fi

#### SET VARIABLES ####
# PyPi URL depends on whether Building Live or Dev
if [ $BUILD_LIVE = true ]; then
  PYPI_HOST=live_pypi.XXXX.YYYY.jisc.ac.uk   # URL for Live package deposits
  TARGET=LIVE
else
  PYPI_HOST=dev_pypi.XXXX.YYYY.jisc.ac.uk    # URL for Dev package deposits
  TARGET=DEV
fi
PYPI_URL=http://${PYPI_HOST}

#### DIAGNOSITICS ####
echo -e "\n*** Diagnostics ***"
echo -e "* Workspace: $WORKSPACE"
echo -e "* Path: $PATH"
echo -e "* Git Branch: $GIT_REF"
echo -e "* Target: $TARGET."
echo -e "* PyPi URL: $PYPI_URL."

APP_DEPLOY_OPTIONS="jper xweb xapi scheduler scheduler-ftp harvester sword-out store sword-in"
# NB. 'store' is left out of this list, because the keyword 'store-app' differs from the service name 'store';
#     'scheduler-ftp' is left out for similar reason
APP_EXEC_OPTIONS="jper xweb xapi scheduler harvester sword-out sword-in"

INSTALL_PATH=/usr/local/PubRouter
echo -e "* Install path: $INSTALL_PATH."

DEPLOYMENT_PATH=${INSTALL_PATH}/deployment
echo -e "* Deployment path: $DEPLOYMENT_PATH."

PUBROUTER_CFG_DIR=/home/jenkins/.pubrouter
JENKINS_SCRIPTS_DIR=/home/jenkins/scripts
TMP_ARCHIVE_DIR=/Incoming/tmparchive
FTP_TMP_DIR=/Incoming/ftptmp
FTP_ERROR_DIR=/Incoming/ftperrors
STORE_MAIN_DIR=/Incoming/store
REPORTSDIR=/var/pubrouter/reports
# STORE_LOCAL_DIR=/var/pubrouter/local_store/live
STORE_TMP_DIR=/var/pubrouter/local_store/tmp
LOG_DIR=/var/log/pubrouter

#### Install sudoers file
echo -e "*** Installing sudoers file"
# Try to copy & rename sudoers file to /etc/sudoers.d directory - failure will be picked up below
sudo cp ${WORKSPACE}/deployment/etc_sudoers-d_jenkins /etc/sudoers.d/jenkins
### CHECK that sudoers file has been installed on server (needs to be done manually by root user)
if [ $? -ne 0 ]; then
  echo -e "\n*** WARNING: 'etc_sudoers-d_jenkins' file could NOT be installed as '/etc/sudoers.d/jenkins' file ."
  echo -e "\n*** '${WORKSPACE}/deployment/etc_sudoers-d_jenkins' must be installed as file named: '/etc/sudoers.d/jenkins' and given '0440' permissions: sudo chmod 0440 /etc/sudoers.d/jenkins\n\n"
  exit 1
fi

#### CREATE DIRECTORIES ####

# Create directories if needed
echo -e "\n*** Creating directories (if necessary)..."
[[ ! -d $LOG_DIR ]] && sudo mkdir -p $LOG_DIR && sudo chown jenkins:jenkins $LOG_DIR
[[ ! -d $PUBROUTER_CFG_DIR ]] && mkdir -p $PUBROUTER_CFG_DIR
[[ ! -d $JENKINS_SCRIPTS_DIR ]] && mkdir -p $JENKINS_SCRIPTS_DIR
# [[ ! -d $STORE_LOCAL_DIR ]] && mkdir -p $STORE_LOCAL_DIR
[[ ! -d $STORE_TMP_DIR ]] && sudo mkdir -p $STORE_TMP_DIR && sudo chown jenkins:jenkins $STORE_TMP_DIR
# If scheduler is deployed on any server
if [[ $SERVICES =~ scheduler ]]; then
  [[ ! -d $TMP_ARCHIVE_DIR ]] && sudo mkdir -p $TMP_ARCHIVE_DIR && sudo chown jenkins:jenkins $TMP_ARCHIVE_DIR
fi
# If scheduler is deployed on FTP server
if [[ $SERVICES =~ scheduler-ftp ]]; then
  [[ ! -d $FTP_TMP_DIR ]] && sudo mkdir -p $FTP_TMP_DIR && sudo chown jenkins:jenkins $FTP_TMP_DIR
  [[ ! -d $FTP_ERROR_DIR ]] && sudo mkdir -p $FTP_ERROR_DIR && sudo chown jenkins:jenkins $FTP_ERROR_DIR
  [[ ! -d $REPORTSDIR ]] && sudo mkdir -p $REPORTSDIR  && sudo chown jenkins:jenkins $REPORTSDIR
fi
# If store is deployed on server (SERVICES contains either "no-store" or "store-app"
[[ $SERVICES =~ store ]] && [[ ! -d $STORE_MAIN_DIR ]] && sudo mkdir -p $STORE_MAIN_DIR && sudo chown jenkins:jenkins $STORE_MAIN_DIR


#### COPY MISCELLANEOUS SCRIPT FILES TO TARGET '/home/jenkins/scripts' DIRECTORY ####
echo -e "\n*** Copying install files from ${WORKSPACE}/scripts/... to ${JENKINS_SCRIPTS_DIR}..."
cp ${WORKSPACE}/scripts/* ${JENKINS_SCRIPTS_DIR}

#### COPY FILES FROM INDIVIDUAL 'APP/deployment' DIRECTORIES TO TARGET '$INSTALL_PATH/deployment' DIRECTORY ####

# Deployment directory - shell scripts, cron jobs and config files used by Supervisor and other tools #
rm -rf ${INSTALL_PATH:?}/*
echo -e "\n*** Creating '${DEPLOYMENT_PATH}' directory"
sudo mkdir -p ${DEPLOYMENT_PATH} && sudo chown -R jenkins:jenkins ${INSTALL_PATH}    # chown INSTALL_PATH & DEPLOYMENT_PATH


# Now copy deployment directories depending on Services required to run on server
echo -e "\n*** Copying install files from ${WORKSPACE}/deployment/... to ${DEPLOYMENT_PATH}..."
cp ${WORKSPACE}/deployment/supervisord.conf ${DEPLOYMENT_PATH}
cp -r ${WORKSPACE}/deployment/shellscripts ${DEPLOYMENT_PATH}   # Copy shellscripts directory

for APP in $APP_DEPLOY_OPTIONS; do
  # If a app option is found within $SERVICES string, copy its deployment files
  [[ $SERVICES =~ $APP ]] && echo -e " - $APP" &&  cp ${WORKSPACE}/deployment/${APP}/* ${DEPLOYMENT_PATH}
done

### COPY & RENAME CRON JOB FILES ###

# If any *.cron files exist
if test -n "$(find $DEPLOYMENT_PATH -type f -name '*\.cron' -print -quit)"; then
  echo -e "\n*** Installing CRON files (*.cron) into '/etc/cron.d/' directory."
  # Copy cron job scripts to /etc/cron.d  THEN Remove the ".cron" suffix because cron.d files cannot have '.' in the
  # file-names (-f forces rename if file already exists)
  sudo cp ${DEPLOYMENT_PATH}/*.cron /etc/cron.d/  &&  sudo rename -f 's/\.cron$//' /etc/cron.d/*.cron
  if [ $? -ne 0 ]; then
    echo -e "\n*** WARNING: Could NOT deploy '${DEPLOYMENT_PATH}/*.cron' files to '/etc/cron.d/' directory and remove the '.cron' suffix."
    echo -e "\n*** If it likely that sudoers file: '/etc/sudoers.d/jenkins' is not deployed or does not contain 'cp' and 'rename' permissions.\n"
    exit 1
  fi
fi
### COPY SUPERVISOR CONF FILES ###

echo -e "\n*** Installing supervisorctl config files into '/etc/supervisor/conf.d' directory for these services:"
sudo rm /etc/supervisor/conf.d/*    # Remove previous config
sudo cp ${DEPLOYMENT_PATH}/supervisord.conf /etc/supervisor/
for APP in $APP_EXEC_OPTIONS; do
  # If a app option is found within $SERVICES string, copy it's Supervisor conf file to /etc/supervisor/conf.d directory
  [[ $SERVICES =~ $APP ]] && echo -e " - $APP" && sudo cp ${DEPLOYMENT_PATH}/${APP}.conf /etc/supervisor/conf.d
done
[[ $SERVICES =~ store-app ]] && echo -e " - store" && sudo cp ${DEPLOYMENT_PATH}/store.conf /etc/supervisor/conf.d


#### SET ENVIRONMENT FOR FLASK ####

echo -e "\n*** Adding .flaskenv file and checking that OPERATING_ENV environment variable is set to '$SERVER_ENV'."
# Add .flaskenv file to set Environment variable OPERATING_ENV
echo "OPERATING_ENV='$SERVER_ENV'" > "$DEPLOYMENT_PATH/.flaskenv"

### Ensuring OPERATING_ENV environment variable is also set to required environment ###
PRO_FILE=~/.bash_profile
SET_ENV="export OPERATING_ENV=$SERVER_ENV"
ENV_VAL=""

# If .bash_profile file exists, grab any lines containing 'OPERATING_ENV'
if [ -f $PRO_FILE ]; then
  # test if OPERATING_ENV is being set in profile file
  ENV_VAL="`grep 'OPERATING_ENV' $PRO_FILE`"
fi

##
### Function to write message, 1 parameter: adverb
##
function fn_env_msg { echo -e "*** Environment variable OPERATING_ENV=${SERVER_ENV} $1 set in $PRO_FILE"; }

# OPERATING_ENV already being set correctly in .bash_profile
if [ "$ENV_VAL" == "$SET_ENV" ]; then
  fn_env_msg "already"
else
  # OPERATING_ENV is not empty, it is being set to wrong value
  if [ -n "$ENV_VAL" ]; then
    echo -e "\n*** WARNING: Wrongly set environment variable $ENV_VAL removed from $PRO_FILE ***\n"
    # strip out lines with OPERATING_ENV from original .bash_profile (creating .bak backup in process)
    sed -i.bak '/OPERATING_ENV/d' $PRO_FILE
  fi
  # Append environment value setting to .bash_profile file
  echo $SET_ENV >> $PRO_FILE
  fn_env_msg "now"
fi
### end OPERATING_ENV processing ###


cd ${PUBROUTER_CFG_DIR:?}

# Create symlink for directory 'sh' in $PUBROUTER_CFG_DIR that points to the 'deployment' directory (If it doesn't already exist)
rm sh   # Remove symbolic link
ln -s $DEPLOYMENT_PATH/shellscripts sh  && echo -e "\n*** Created symlink in $PUBROUTER_CFG_DIR:  ln -s $DEPLOYMENT_PATH/shellscripts sh"


echo -e "\n*** Setting executable permissions on  *.sh  files in ${PUBROUTER_CFG_DIR}/sh/ ..."
sudo chmod +x ${PUBROUTER_CFG_DIR}/sh/*.sh

#### SET APP DEPENDENT CONFIGURATION (in /home/jenkins/*.cfg files) ####

echo -e "\n*** Setting configuration (in *.cfg files) according to which services are deployed on server...\n"

##
### Function to process config file(s) - (1) Remove specified config item from file; (2) Write new config item to file.
### Takes 3 Parameters
##
function fn_update_config {
  # $1 - Config keyword
  # $2 - New config value
  # $3 - Filename of config file to update
  # Remove lines containing Config-keyword from all config (*.cfg) files
  echo -e "\n** Removing config $1 from ALL *.cfg files: "
  sed -i.bak "/$1/d" *.cfg
  # Append new config to local config files as needed
  NEW_CONFIG="$1 = $2"
  echo $NEW_CONFIG >> $3
  echo -e "\n** Added config '$NEW_CONFIG' to $3"
}

## Set STORE_TYPE ##
# Set STORE_TYPE_STR to "local" or "remote" depending on whether store service is being run locally on server or not
# If store is deployed on server (SERVICES contains either "no-store" or "store-app"
[[ $SERVICES =~ store ]] && STORE_TYPE_STR='"local"' || STORE_TYPE_STR='"remote"'
fn_update_config 'STORE_TYPE' "$STORE_TYPE_STR" global.cfg

## Set SERVER_ID (from Jenkins NODE_NAME environment variable) ##
# Note: ${NODE_NAME##* } returns the last word in a space or under_score separated string, so 'PubRouter Staging App2' --> 'App2'
# We surround SERVER_ID with double quotes
SERVER_ID='"'${NODE_NAME##*[_ ]}'"'
fn_update_config 'SERVER_ID' "$SERVER_ID" global.cfg

## Set WEB_API_TYPE in jper.cfg ##
# Indicates whether web GUI is being provided by web_main or xweb_main
if [[ $SERVICES =~ jper ]]; then
  WEB_API_TYPE='"jper"'
elif [[ $SERVICES =~ xweb ]]; then
  WEB_API_TYPE='"xweb"'
elif [[ $SERVICES =~ xapi ]]; then
  WEB_API_TYPE='"xapi"'
else
  WEB_API_TYPE='"none"'
fi
fn_update_config 'WEB_API_TYPE' "$WEB_API_TYPE" jper.cfg


## Set SCHEDULER_JOBS (if scheduler being deployed)
if [[ $SERVICES =~ scheduler ]]; then
  # Create python list of strings from '|' separated word string - every occurrence of '|' is replaced by ' '
  for JOB in ${SCHEDULER_JOBS//|/ }; do
    # Add double-quoted JOB followed by ', ' to JOB_STR - expressed as python logic: JOBS_STR += '"{}", '.format($JOB)
    JOBS_STR=${JOBS_STR}'"'${JOB}'", '
    #JOBS_STR="${JOBS_STR}\"${JOB}\", "
  done
  # Remove trailing ", " and bracket the result '['...']'
  JOBS_STR='['${JOBS_STR%', '}']'
  fn_update_config 'SCHEDULER_JOBS' "$JOBS_STR" jper.cfg
fi

#### CREATE VIRTUAL ENVIRONMENT & INSTALLING APPS ####

echo -e "\n*** Collecting & installing application versions..."

echo -e "\n** Creating venv (app)...\n"
cd ${INSTALL_PATH} || exit 1
rm -rf app
python3 -m venv app
. app/bin/activate

# Upgrade pip
#pip install --upgrade pip

# Running JPER API app or Store app or sword-in - need 'gunicorn' web-server
[[ $SERVICES =~ jper|xweb|xapi|store-app|sword-in ]] && pip install gunicorn

# Install Router PyPi module (from our own PyPi repository)
VERSION="$(cat $WORKSPACE/VERSION)"
echo -e "** Installing router version: $VERSION"
pip install --verbose --extra-index-url ${PYPI_URL}'/simple/' --trusted-host ${PYPI_HOST} router==$VERSION
echo -e "\n** Router installed\n"


#### RUN THE APPLICATION SERVICES (via supervisorctl) ####

echo -e "\n*** Notifying supervisor and restarting application services..."
sudo supervisorctl stop all
sudo supervisorctl reread
sudo supervisorctl update

# Store service keywords don't match service name, so handle individually - store should be started first
if [[ $SERVICES =~ store-app ]]; then
  sudo supervisorctl start store || exit $?
elif [[ $SERVICES =~ no-store ]]; then
  echo -e "\n** NOT running store app on any server (assume all other services are running on 1 server) **\n"
fi
for APP in $APP_EXEC_OPTIONS; do
  if [[ $SERVICES =~ $APP ]]; then
    sudo supervisorctl start $APP || exit $?
  fi
done

echo -e "\n*** Supervisor status:"
sudo supervisorctl status
echo -e "\n---- End of deployment script ----\n\n"
# end #
