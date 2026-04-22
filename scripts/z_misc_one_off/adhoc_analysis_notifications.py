#!/usr/bin/env python
"""
Analyse all notifications in database to ....

"""
import os
from octopus.core import initialise
from octopus.lib.dates import now_str
from router.jper.app import app     # need to import app_decorator as other modules import it from here.
from router.shared.models.note import RoutedNotification

log_fname = os.path.join("/tmp", f"notification_adhoc_analysis_{now_str('%Y-%m-%d')}.txt")
log_file = open(log_fname, "w", encoding="utf-8")


def write_log(s):
    print(s)
    log_file.write(s + "\n")


def format_output(_set, sep="\n "):

    return sep + sep.join(sorted(_set)) + "\n"


write_log(f"\nResults will be written to file: {log_fname}\n")


def check_for_whitespace(tmp, field):
    if field:
        bad_char = []
        for char, desc in [("\n", "NL"), ("\r", "CR"), ("\t", "TAB")]:
            if char in field:
                bad_char.append(desc)
        if bad_char:
            tmp.append(f"{k.title()}: {bad_char} {field}")
            return " ".join(field.split())
    return field


with app.app_context():

    initialise()
    org_names = {}

    scroller = RoutedNotification.routed_scroller_obj(scroll_num=99)
    with scroller:
        count = 0
        bad = 0
        for note in scroller:
            count += 1
            if (count % 1000) == 0:
                print(f"Processed {count}")

            tmp = []
            for auth in note.authors:
                for aff in auth.get("affiliations", []):
                    org = aff.get("org")
                    if org:
                        org = check_for_whitespace(tmp, org)
                        try:
                            org_names[org].append(note.id)
                        except KeyError:
                            org_names[org] = [note.id]
                    for k in ["dept", "raw"]:
                        check_for_whitespace(tmp, aff.get(k))

            if tmp:
                bad += 1
                write_log(f"\n**** Note {note.id}\n  " + "\n  ".join(tmp))

        write_log(f"\n**** Found {bad} notifications with problematic whitespace {count} Notifications ****\n")

        write_log(f"\n**** Structured Aff Organisation Name Values (sorted) x{len(org_names)} ****\n")
        for k in sorted(org_names.keys()):
            write_log(f"{k} :: {org_names[k]}")

        write_log(f"\n**** DONE ****\n")
