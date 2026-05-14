#!/bin/bash
# Move log files to /tmp folder and delete files from incoming folders
#   PARAMS:
#       username
#
# Ensure this script is executable can be run as sudo without password by the software
# by adding an entry in `/etc/sudoers.d/jenkins`, like:
# jenkins ALL = (root) NOPASSWD:/home/jenkins/.pubrouter/sh/move_logs_n_delete_incoming.sh
# ----------------------------------------------------------------------------------------------
username=$1 # This is typically a long hex-string

incoming_archive=/Incoming/tmparchive
incoming_temp=/Incoming/ftptmp
logdir=/var/log/pubrouter

function num_files {
        numfiles=`ls -1 $1 | wc -l`
}

function remove_files {
        path=$1
        [ -d $path ] && num_files $path && [[  $numfiles -gt 0 ]] && rm -rf $path/* && echo "Removed $numfiles files from  $path"
}

# Move logfiles if any exist
num_files $logdir
[[ $numfiles -gt 0 ]] && mv $logdir/* /tmp/
echo "$numfiles log files moved to /tmp directory"

# remove files
remove_files $incoming_archive/$username
remove_files $incoming_temp/$username

exit 0
#end#