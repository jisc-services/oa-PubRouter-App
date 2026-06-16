#!/usr/bin/env python
"""
Analyse all notifications in database to determine how providers provide affiliations.

Report:
    Total no of notifications each of them provided in last 90 days; then, from these…
    Total no of author affiliations these contained; of these…
    % of affiliations that lack org
    % of affiliations that have none of org, city, country.
    % of affiliations that lack org ID.
    % of affiliations that have neither org nor org ID.
    % of affiliations that have none of org, city, country, org ID.
    List the providers in decreasing order of (3) above.

Output:
    - CSV file
Calling convention:
    ./report_all_note_provider_aff_usage.py   --> Outputs a log file: /tmp/notification_analysis_{YYYY-MM-DD}.txt
    ./report_all_note_provider_aff_usage.py log-file-path-name   --> Outputs log to provided log-file-path-name
"""
import sys
from octopus.core import initialise
from router.jper.app import app     # need to import app_decorator as other modules import it from here.
from router.jper.reports import provider_aff_usage_report


if __name__ == "__main__":

    arg_v = sys.argv
    # No command line argument given
    if len(arg_v) == 1:
        # Create default log file pathname
        csv_path_name = None
    else:
        csv_path_name = arg_v[1]

    with app.app_context():
        initialise()
        fname = provider_aff_usage_report(csv_path_name, print_it=True)
        print("CSV output written to file:", fname)
