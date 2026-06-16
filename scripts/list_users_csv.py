#!/usr/bin/env python
"""
List users, output as CSV file.

Can provide command line argument that specifies Type of Org accounts to list users for, by concatenating
characters from set: [A, R, P] (Admin, Repository, Publisher accounts).

If no command line arg supplied, then you will be prompted to enter the same.
"""
import sys
from octopus.lib.csv_files import create_csv_file
from octopus.core import initialise
from router.jper.app import app     # need to import app_decorator as other modules import it from here.
from router.shared.models.account import AccUser

arg_v = sys.argv
allowed_types = "[A, R, P]"
# No command line argument given
if len(arg_v) == 1:
    org_type = input(f"** Organisation Type NOT provided on command line.\n\n** Enter Organisation Type char(s) from {allowed_types}, possibly concatenated: ")
else:
    org_type = arg_v[1]
if not org_type:
    exit(0)

org_type = org_type.upper()
# Validate org_type
for c in org_type:
    if c not in "ARP":
        print(f"\n!!! ERROR: Organisation Type must be one or a combination of characters {allowed_types}. ('{org_type}' was input). !!!\n\n")
        exit(1)


def user_acc_to_data_row(user):
    org = user.acc_org
    live_timestamp = org.live_date or ""
    deleted_timestamp = user.deleted_date or ""
    # For email we use a function because email may come from username or email field.
    return [org.role_short_desc(org.raw_role), "Deleted" if org.deleted_date else "Off" if org.status == 0 else "On",
            org.org_name, live_timestamp[:10], user.surname, user.forename,
            user.org_role, user.get_email(), user.role_short_desc, deleted_timestamp[:10]]


with app.app_context():
    initialise()
    headings = ["Org. Type", "Org. Status", "Org. Name", "Live Date", "Surname", "Firstname", "User's Role", "Email", "Router Role", "Deleted date"]
    data_rows = AccUser.pull_all_user_n_org_accounts(org_types=org_type, live_test="L", list_func=user_acc_to_data_row)
    # Sort by Org-type, org-status, ORG-NAME, SURNAME
    data_rows.sort(key=lambda k: (k[0], k[1], k[2].upper(), k[4].upper()))
    file_path = f"/tmp/users_of_org_types_{org_type}.csv"
    # Create file
    num_recs = create_csv_file(file_path, data_rows, headings)
    print(f"\n\n*** Report '{file_path}' created for {num_recs} users of organisations of type(s): {list(org_type)} ***\n\n")
