#!/usr/bin/env python
"""
Script to create UNIX user accounts and required SFTP directories for PUBLISHERS.

This script is intended to be run after redeploying Publications Router App1 onto a NEW SERVER.

RUNNING THE SCRIPT:

    # Must be 'jenkins' user
    su - jenkins
    source /usr/local/PubRouter/app/bin/activate
    # Run script
    python3 -m scripts.create_publisher_dirs

"""
import os
from router.shared.models.account import AccOrg
from router.jper.app import app

# SFTPUSERS home directory must be created by root user
# (under which the user account directories (named after user ID) will be created)
sftp_root = '/home/sftpusers'
true_sftp_root = '/Incoming/sftpusers'
if not os.path.exists(sftp_root):
    print("\n**** ERROR: directory '{d}' does not exist - IMPORTANT: This is a sym-linked directory to {t}.\n\n     You must create it (as root user): `mkdir {t}; ln -s {t} {d}`.\n".format(d=sftp_root, t=true_sftp_root))
    exit(1)

with app.app_context():
    print("\n\n**** Creating Publisher UNIX users and FTP directories ****")
    for live_publisher in AccOrg.get_publishers():
        try:
            print("\n*** Creating account & dirs for publisher: ID: {} Name: {}".format(live_publisher.id, live_publisher.org_name))
            live_publisher.create_ftp_account()
        except Exception as e:
            print("--- ERROR: Failed to create account: ", str(e))
