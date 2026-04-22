#!/bin/bash
#---------------------------------------------------------------------------------
# Kills any sftpusers SFTP connections that have existed for longer than CUTOFF duration.
#
# - finds all active SFTP connections for users in Group 'sftpusers'
# - Extracts Parent-PID, Username (hex string), and elapsed time in secs
# - kills the Parent PID (which then also destroys the @notty process)
#
# Params:
#       $1 = Cutoff duration in hours
#       $2 = Logfile [optional] (Script will echo to stdout if omitted).
# Returns:
#       0 - no problems
#       3 - problem with parameters
#       1 or other non-zero - some other OS error
#---------------------------------------------------------------------------------
# Params
CUTOFF_HRS=${1-}
LOG_FILE=${2-}

# Constants
PARAM_ERR_CODE=3

# Function: log(msg)
function log_err {
  # Echo to stderr
  echo -e "ERROR: $1" >&2
  # If log file, then echo to it
  if ! [ -z "$LOG_FILE" ]; then
    echo -e "ERROR: $1" >>$LOG_FILE
  fi
}

# Function: log(msg)
function log {
  # If no log file, then echo to stdout
  if [ -z "$LOG_FILE" ]; then
    echo -e "$1"
  else
    echo -e "$1" >>$LOG_FILE
  fi
}

if [ $# -lt 1 ]; then
  log_err "You must supply arguments.\nUsage: $0 cutoff-duration-hours [ logfile-path ]\n"
  exit $PARAM_ERR_CODE
fi



# Check hours is an integer
if ! [[ $CUTOFF_HRS =~ ^[0-9]+$ ]]; then
  log_err "Cutoff duration '$CUTOFF_HRS' was not numeric"
  exit $PARAM_ERR_CODE
fi

# Get list of active SFTP connections, in bespoke Ouput format:
#  Parent-PID, User, Elapsed-time-seconds, Command (with :width specifiers)
# Select those with "@notty" in them.
# Remove leading spaces, then replace (multiple) spaces by single '-'
PROCESS_INFO=$(ps -G sftpusers -o ppid,user:40,etimes,cmd:50 | grep 'sshd:[^@]*@notty' | sed -e 's/^ *//'  -e 's/  */-/g')
COUNT=0

# Get timestamp in format: YYYY-MM-DD HH:MM:SS
DATE_TIME=$(date -Iseconds | cut -c1-19 | tr 'T' ' ')

log "\n$DATE_TIME Running: $0. (Kill SFTP sessions older than $CUTOFF_HRS hours)."

# Loop through list of PIDS
for INFO in $PROCESS_INFO; do
  # Read $INFO into 4 variables PID, USER, ELAPSED_SECS, CMD  using field separator of '-'
  IFS='-' read PID USER ELAPSED_SECS CMD <<< $INFO

  # Convert Seconds to hours (rounded down)
  let HOURS=$ELAPSED_SECS/3600

  # If SFTP process has been active for more than prescribed duration
  if (( $HOURS >= $CUTOFF_HRS )); then
    log " Killing SFTP connection $PID for user ${USER}, active for ~$HOURS hours."
    kill $PID
    let COUNT++
  else
    log " Left SFTP connection $PID for user ${USER}, active for ~$HOURS hours."
  fi
done

if (( $COUNT > 0 )); then
  # If we have killed any sessions, allow 1 second for kill processing to complete
  sleep 1
fi

log "Killed $COUNT SFTP connection(s)."
# end #

