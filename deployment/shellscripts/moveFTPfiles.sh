#!/bin/bash
# Calling convention:
#    moveFTPfiles.sh  username newowner target_tmp_dir unique_id thefile safety_dir
#
# Move specified file from a users ftp jail directory to target temporary directory where they will be processed
# set the owner and permissions to something that the scheduler will be allowed to move 
# e.g. same owner as the one that is going to be running the script would be good
# Ensure this script is executable can be run as sudo without password by the software
# by adding an entry in `/etc/sudoers.d/jenkins`, like:
#   jenkins ALL = (root) NOPASSWD:/home/jenkins/.pubrouter/sh/moveFTPfiles.sh
# -------------------------------------------------------------------------
username="$1" # get from script params
newowner="$2"
target_tmp_dir="$3"
unique_id="$4"
thefile="$5"
tmp_archive="$6"

# if safety directory is NOT empty
if [ ! -z "$tmp_archive" ]; then
    # copy everything to archive directory so there is an original copy of everything received before processing by the system
    archive_location="$tmp_archive/$username/$unique_id"
    mkdir -p "$archive_location"
    cp -R "$thefile" "$archive_location"
    # Chown to tmparchive owner
    chown -R "$newowner":"$newowner" "$archive_location"
fi

target_dir="$target_tmp_dir/$username/$unique_id"
# Create target directory
mkdir -p "$target_dir"
# move the specified file in the jail to the temp processing directory
mv "$thefile" "$target_dir"
# set ownership for all files in the user directory under target_tmp_dir
chown -R "$newowner":"$newowner" "$target_tmp_dir/$username"
# end #
