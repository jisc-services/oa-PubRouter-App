#!/bin/bash
# Calling convention:
#    deleteFTPuser.sh  username
#
# Delete an ftp user and their jail folder plus any contents.
# Ensure this script is executable can be run as sudo without password by the software
# by adding an entry in `/etc/sudoers.d/jenkins`, like:
#   jenkins ALL = (root) NOPASSWD:/home/jenkins/.pubrouter/sh/deleteFTPuser.sh
# -------------------------------------------------------------------------

username=$1 # get from script params

deluser $username
rm -R /home/sftpusers/$username
if [ $? -eq 0 ]; then
  echo -e "User '$username' has been deleted from the system!\n\nNow deleting other directories"
  # Now delete other locations under /Incoming directory
  dirs="sftpusers tmparchive ftperrors ftptmp"
  for dir in $dirs; do
    target="/Incoming/$dir/$username"
    # Attempt to remove directory, but if it doesn't exist then ignore error
    [ -d $target ] && rm -R $target && echo -e "\nDeleted directory: $target" || true
  done
else
  echo -e "Failed to delete user '$username'!\n"
fi
