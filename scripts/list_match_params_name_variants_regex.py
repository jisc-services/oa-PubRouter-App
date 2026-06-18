#!/usr/bin/env python

"""
Script for extracting & printing name variants that contain Regex
"""

from router.shared.models.account import AccRepoMatchParams, AccOrg
from router.jper.app import app

WITH_HTML = False
sep = "<br>" if WITH_HTML else "\n"
sep_list = "<br>" if WITH_HTML else ""
sep_title = "" if WITH_HTML else "\n"
tab = " &nbsp; &nbsp;" if WITH_HTML else "\t"

with app.app_context():
    print("*** Institutions with RegEx in Matching Parameter Name Variants ***")
    if WITH_HTML:
        print("<table><tbody>")
    for match_params in AccRepoMatchParams.pull_all(for_update=False):
        if match_params.has_regex:
            if WITH_HTML:
                print("<tr><td>")

            org_acc = AccOrg.pull(match_params.id)
            print(f"{sep_title}{sep_title}** {org_acc.org_name} **{sep}")
            for name_var in match_params.name_variants:
                print(f"{tab}{name_var}{sep_list}")

            orig_names = match_params.orig_name_variants
            if orig_names:
                print(f"{sep}  Original names (some replaced by RegEx):{sep_list}")
                for orig_name in orig_names:
                    print(f"{tab}{orig_name}{sep_list}")
            else:
                print(f"{sep}  No original names are saved")

            if WITH_HTML:
                print("</td><td></td></tr>")

    if WITH_HTML:
        print("</tbody></table>")
