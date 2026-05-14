#!/bin/bash
# Calling convention:
#    checkFtpSessionExists.sh  username
#
# Confirm whether any SFTP sessions exist for a user

# -------------------------------------------------------------------------
username="$1" # get from script params

# Self defined shell-script exit code
SIGNED_IN_EXIT_CODE=5     # code returned if an SFTP user has an active connection

# check that user we're checking isn't currently signed in (and thus in the process of depositing files)
signed_in_user=`ps -f -G sftpusers | grep "sshd: ${username}@notty"`
if [[ $signed_in_user ]]; then
    #  echo "User is currently signed in."
    exit $SIGNED_IN_EXIT_CODE
else
    exit 0  # No FTP session exists for user
fi
# end #