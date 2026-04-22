#!/bin/bash
# Calling convention:
#    createFTPuser.sh  username
#
# Create an sftp user and jail them, using username and password provided as script args
# this script also requires mkpasswd to be installed - sudo apt-get install whois will get it.
# Ensure this script is executable can be run as sudo without password by the software
# by adding an entry in `/etc/sudoers.d/jenkins`, like:
#   jenkins ALL = (root) NOPASSWD:/home/jenkins/.pubrouter/sh/createFTPuser.sh
# -------------------------------------------------------------------------

username=$1 # get from script params

egrep "^$username" /etc/passwd >/dev/null
if [ $? -eq 0 ]; then
  echo -e "\nOOPS: $username already exists!"
  exit 1
else
  BASE_DIR=/home/sftpusers
  password=$2 # get this from script params
  encryptedPassword=$(mkpasswd -m sha-512 $password)
  useradd -g sftpusers -p $encryptedPassword --base-dir $BASE_DIR -s /sbin/nologin $username
  if [ $? -eq 0 ]; then
    echo -e "\nUser $username has been added to system!"
  else
    echo -e "\nFailed to add user: $username!"
    exit 1
  fi
  # Create 3 directories and set their permissions
  USER_DIR=$BASE_DIR/$username
  DIRS="$USER_DIR $USER_DIR/xfer $USER_DIR/atypon_xfer"
  for DIR in $DIRS; do
     mkdir $DIR
     [ $? -eq 0 ] && echo -e "\n Created directory: $DIR" || echo -e "\n FAILED to create directory: $DIR"
     # Change ownership only for sub-directories
     if [[ "$DIR" != "$USER_DIR" ]]; then
       chown $username:sftpusers $DIR
       [ $? -eq 0 ] && echo " Set ownership to $username:sftpusers" || echo " FAILED to set ownership to $username:sftpusers"
     fi
  done
fi
