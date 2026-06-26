#!/usr/bin/env python

"""
Script for dumping matching parameters for ALL (Live & Test) Repositories to individual CSV & JSON files - 1 of each
for each institution.

Files are created in directory specified by `output_path` variable, and are named after the institution.
"""
import os
from json import dump
from zipfile import ZipFile, ZIP_DEFLATED
from octopus.lib.csv_files import create_csv_file, create_in_memory_csv_file
from router.shared.models.account import AccRepoMatchParams, AccOrg, REPO_MATCH_PARAM_SCROLL_NUM, CONN_CLOSE, DICT
from router.jper.app import app

output_path = os.path.join(os.sep, "tmp", "match_params")

def delete_dict_fields(_dict, fields):
    """
    Attempt to delete elements from dict, ignore KeyError (field not in dict)
    """
    for _field in fields:
        try:
            del _dict[_field]
        except KeyError:
            pass

def write_json_file(out_path_no_suffix, org_name, mp_dict):
    """
    Create JSON file.
    """
    mp_dict["org_name"] = org_name
    mp_dict["has_regex"] = mp_dict.get("has_regex") == 1
    # If no Original-name-variants, delete the dict entry (if it exists)
    if not mp_dict.get("orig_name_variants"):
        delete_dict_fields(mp_dict, ["orig_name_variants"])

    out_file = f"{out_path_no_suffix}.json"
    ## Create json file of results ##
    with open(out_file, "w", encoding='utf-8') as json_file:
        dump(mp_dict, json_file, indent=4)
    print(f"  * Created file: {out_file}")

def write_csv_file(out_path_no_suffix, org_name, mp_dict):
    """
    Create CSV file (in Router's expected format)
    """

    out_file = f"{out_path_no_suffix}.csv"
    create_csv_file(out_file,
                    AccRepoMatchParams.csv_row_generator(mp_dict.get("matching_config")),
                    AccRepoMatchParams.csv_row_headings()
                    )
    print(f"  * Created file: {out_file}")


with app.app_context():

    os.makedirs(output_path, exist_ok=True) # Make directory tree (if not already existing)

    print("*** Outputting matching parameters - 1 JSON file & 1 CSV file per institution. ***")
    print(f" ** Files will be written to: {output_path} directory")

    # In Org names we will replace spaces by underscore, & remove any of these chars: '-,()/\.&
    org_translate_tbl = str.maketrans(" ", "_", "'-,()/\\.&")

    # Load all Repo organisation names into a dict.
    repo_acc_ids_dict = AccOrg.get_account_id_to_org_names_dict("R", live_test="LT", close_cursor=True)

    with ZipFile(
            os.path.join(output_path, "all_match_params.zip"),
            "w",
            compression=ZIP_DEFLATED) as match_params_zip:

        num_recs = 0
        match_param_scroller = AccRepoMatchParams.scroller_obj(
            pull_name="all_repo", rec_format=DICT, scroll_num=REPO_MATCH_PARAM_SCROLL_NUM, end_action=CONN_CLOSE)
        with match_param_scroller:
            for mp_dict in match_param_scroller:
                org_name = repo_acc_ids_dict.get(mp_dict["id"], 'MISSING')
                file_path_no_suffix = os.path.join(output_path, org_name.translate(org_translate_tbl).lower())
                # print(f"  * {file_path_no_suffix}")
                print(f"\n*** Creating files for {org_name} ***")

                # Not interested in these fields
                delete_dict_fields(mp_dict, ("id", "created", "updated", "had_regex"))

                # Create JSON file FIRST because CSV file creation pops items from mp_dict
                write_json_file(file_path_no_suffix, org_name, mp_dict)

                row_count, csv_file = create_in_memory_csv_file(
                    data_iterable=AccRepoMatchParams.csv_row_generator(mp_dict.get("matching_config"), preserve_data=True),
                    heading_row=AccRepoMatchParams.csv_row_headings(),
                    return_bytes_io=False
                )
                match_params_zip.writestr(os.path.basename(file_path_no_suffix) + ".csv", csv_file.read())

                # Must create CSV file AFTER JSON file, as it pops items from mp_dict
                write_csv_file(file_path_no_suffix, org_name, mp_dict)

                num_recs += 1

        del match_param_scroller  # Delete here to clear down any memory


    print(f"\n*** Completed - {num_recs} institutions processed. Files are in: {output_path} directory. ***")


