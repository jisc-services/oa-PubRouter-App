"""
Development environment configuration file for the JPER application

On deployment, configuration can be overridden by using a local ~/.pubrouter/jper.cfg file
"""
LOGFILE = '/Incoming/logs/jper.log'
SCHEDULER_LOGFILE = '/Incoming/logs/scheduler.log'
PUB_TEST_LOG = '/Incoming/logs/publisher_testing.log'

REPORTSDIR = '/Incoming/reports'

SFTP_KILL_AFTER_X_HOURS=0   # Don't want to run bash script

USERDIR = '/Incoming/sftpusers'

