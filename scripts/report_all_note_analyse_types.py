#!/usr/bin/env python
"""
Analyse all notifications in database to determine range of `type` values for particular fields.

Calling convention:
    ./report_all_note_analyse_types.py   --> Outputs a log file: /tmp/notification_analysis_{YYYY-MM-DD}.txt
    ./report_all_note_analyse_types.py log-file-path-name   --> Outputs log to provided log-file-path-name
"""
import sys
from octopus.core import initialise
from router.jper.app import app     # need to import app_decorator as other modules import it from here.
from router.jper.reports import note_types_report

if __name__ == "__main__":

    arg_v = sys.argv
    # No command line argument given
    if len(arg_v) == 1:
        # Create default log file pathname
        log_file_pathname = None
    else:
        log_file_pathname = arg_v[1]

    with app.app_context():
        initialise()
        note_types_report(log_file_pathname, print_it=True)
