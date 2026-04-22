#!/bin/bash
#---------------------------------------------------------------------------------
# Deletes items from folder that are older than specified number of days
#
# Params:
#     $1 = name of parent executable or process-name
#     $2 = Directory to delete from
#     $3 = Minimum days to keep
#     $4 = Days to keep
# Returns:
#     0 - no problems
#     1 or other non-zero - some other OS error
#---------------------------------------------------------------------------------

TEMP=${1-$0}
SCRIPT=`basename "$TEMP"`

# Function to echo output to stderr
echo_stderr(){
  echo -e "$@" 1>&2;
};

#### Param processing ####

# Must have at least first 4 params passed
if [ $# -lt 4 ]; then
  echo_stderr "Must pass 4 args to script: Parent-executable, Directory-path, Minimum-num-days, Num-days-to-keep"
	exit 1
fi

STORE_DIR=$2
MIN_DAYS_TO_KEEP=$3
DAYS_TO_KEEP=$4

if [ ! -d "$STORE_DIR" ]; then
  echo_stderr "Target directory $STORE_DIR does not exist"
	exit 1
fi

# Need to keep a minimum of 30 days of files
if [ $DAYS_TO_KEEP -ge $MIN_DAYS_TO_KEEP ]; then
    # Find all the directories 1 level below $STORE_DIR that are older than $DAYS_TO_KEEP days
    # Do a recursive, forced, verbose delete (rm -rfv) of each directory
    # Count the number of lines of output (one line per thing deleted)
    # Output any errors to temporary file
    COUNT_DELETED=`find $STORE_DIR -mindepth 1 -maxdepth 1 -type d -mtime +$DAYS_TO_KEEP -exec rm -rfv '{}' \; | wc -l`
    echo -e "[$SCRIPT] Deleted '$STORE_DIR' contents older than $DAYS_TO_KEEP days - Number of files & folders deleted: $COUNT_DELETED."
    exit 0
else
    # Output to the STDERR
    echo_stderr  "[$SCRIPT] Number of days to keep ($DAYS_TO_KEEP) was less than the minimum ($MIN_DAYS_TO_KEEP); no deletion occured."
    exit 1
fi
# End #
