#!/bin/bash
# Calling convention:
#    checkUserExists.sh  username
#
# Confirms that a user account exists on the server by checking whether the passed username is found
# within the /etc/passwd file.

# -------------------------------------------------------------------------
username="$1" # get from script params

# Self defined shell-script exit codes
MISSING_USER_EXIT_CODE=6    # code returned if the user account does not appear in /etc/passwd file

# Check if username exists
egrep "^$username" /etc/passwd >/dev/null
if [ $? -ne 0 ]; then
    # echo "User [$username] NOT FOUND"
    exit $MISSING_USER_EXIT_CODE
else
    exit 0  # User exists
fi
# end #