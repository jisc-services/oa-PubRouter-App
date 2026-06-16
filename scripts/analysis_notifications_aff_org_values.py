#!/usr/bin/env python
"""

Analyse "org" values of all affiliations of all notifications in database
https://www.pivotaltracker.com/story/show/187514417
"""
import os
import re
from octopus.core import initialise
from octopus.lib.dates import now_str
from router.jper.app import app     # need to import app_decorator as other modules import it from here.
from router.shared.models.note import RoutedNotification

org_has_bad_str = re.compile('(Also at|Building|c\/o|C(?:ampus|ent(?:er|re)|hair|ollege.+?University|onsultant)|D(?:ep(?:t|artment)|irectorate|ivision)|F(?:ac(?:ility|ulty)|loor)|Group|House|In(?:itiative|stitute)|L(?:aboratory|ibrar)|Program|Road|S(?:ection|ervice d|chool.+?University)|Team|Unit|(?:,.+?,))')


log_fname = os.path.join("/tmp", f"notification_aff_org_analysis_{now_str('%Y-%m-%d')}.txt")
log_file = open(log_fname, "w", encoding="utf-8")
print(f"\nResults will be written to file: {log_fname}\n")
print_it = True


def write_log(*args):
    if print_it:
        print(*args)
    log_file.write("".join(args))


def format_output(_set, sep="\n "):
    return sep + sep.join(sorted(_set)) + "\n"


# def check_for_whitespace(tmp, field):
#     if field:
#         bad_char = []
#         for char, desc in [("\n", "NL"), ("\r", "CR"), ("\t", "TAB")]:
#             if char in field:
#                 bad_char.append(desc)
#         if bad_char:
#             tmp.append(f"{k.title()}: {bad_char} {field}")
#             return " ".join(field.split())
#     return field


with app.app_context():

    initialise()
    # org_names = {}
    bad_org = set()
    ok_org = set()
    bad_provider = {}
    scroller = RoutedNotification.routed_scroller_obj(scroll_num=99)
    count = 0
    bad_aff = 0
    bad_note = 0
    with scroller:
        for note in scroller:
            count += 1
            if (count % 1000) == 0:
                print(f"Processed {count}")
                if count > 4000:
                    break

            ok = True
            for auth in note.authors:
                for aff in auth.get("affiliations", []):
                    org = aff.get("org")
                    if org:
                        bad_match = org_has_bad_str.search(org)
                        if bad_match:
                            ok = False
                            bad_aff += 1
                            bad_org.add(f"`{org}`")
                        else:
                            ok_org.add(f"`{org}`")
                            # raw = aff.get('raw')
                            # raw = f"\n  (`{raw}`)" if raw else ""
                            # ok_org.add(f"`{org}`{raw}")
            if not ok:
                bad_note += 1
                try:
                    bad_provider[note.provider_agent] += 1
                except KeyError:
                    bad_provider[note.provider_agent] = 1


    write_log(f"\n**** Found problematic {bad_note} notifications (out of {count}) containing {bad_aff} bad orgs ****\n")

    write_log(f"\n**** Orgs providing bad affiliation org values (:: num of bad notifications) ****\n")
    for k in sorted(bad_provider.keys()):
        write_log(f"{k} :: {bad_provider[k]}\n")

    for s, d in (bad_org, "Bad Org names"), (ok_org, "Acceptable Org names"):
        write_log(f"\n\n*** {d} (total: {len(s)}) ***\n")
        for v in s:
            write_log("\n", v)
    write_log(f"\n\n**** DONE ** Results written to file: {log_fname} ****\n")
