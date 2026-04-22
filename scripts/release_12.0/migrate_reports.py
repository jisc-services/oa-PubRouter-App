#!/usr/bin/env python3
# """
# Script to do following:
#   - populate new MySQL database from old ES index
# """

import os
import csv
from datetime import date
from octopus.modules.shared.mysql_db_ddl import JPER_REPORTS_TABLES
from octopus.modules.mysql import utils
from octopus.modules.shared import mysql_dao
from router.jper.app import app

# MIGRATION_ERRORS_FILE = "C:/Incoming/mysql_report_migration_errors.txt"
MIGRATION_ERRORS_FILE = "/tmp/mysql_report_migration_errors.txt"
MYSQL_ADMIN = "admin"
# MYSQL_ADMIN_PWD = "1#er1*<Ss%WE&0QxA]C_mNS[C=0XERBI"    # DEV
MYSQL_ADMIN_PWD = "HuCfbmgVCBLURSMxOrDf"    # Test

# report_dir = "C:/Users/Adam.Rehin/Downloads"
report_dir = "/var/pubrouter/reports"
pub_report_dir = report_dir + "/publishers"

print("* Error file:", MIGRATION_ERRORS_FILE)

error_count = 0
err_file = open(MIGRATION_ERRORS_FILE, "w", encoding="utf-8")

def write_error(table, rec, e):
    global error_count
    error_count += 1
    err_file.write("{}) {} error\n{}\n{}\n\n".format(error_count, table, rec, str(e)))


def read_report_csv(report_file_path_name):
    """
    Function takes a csv report and extracts report data from it.

    :param report_file_path_name: name of the csv file we wish to process
    """
    # read our csv file (if it exists) and save the data as a list
    csv_list = []
    if os.path.exists(report_file_path_name):
        with open(report_file_path_name, "r") as csv_file:
            csv_reader = csv.reader(csv_file)
            # skip the header line, we don't want to include this in our list, as we write our own regardless
            # do this rather than pop from a list, as list element may not exist and cause an exception
            next(csv_reader, None)
            # cast our csv_reader to list, so we can close the csv file and work with a list. Only casts lines
            # which haven't yet been iterated by next() therefore, we miss the header line
            csv_list = list(csv_reader)
    return csv_list

def load_institution_data(report_dir, report_name, map_ac_org_name_to_id):
    report_path = "{}/{}".format(report_dir, report_name)

    # institution report names are of form: "LIVE_monthly_notifications_to_institutions_2017.csv"
    is_live = report_name.startswith("LIVE")
    year = int(report_name[-8:-4])

    print("\n* Migrating {}".format(report_name))

    csv_recs = read_report_csv(report_path)
    print("\nRead {} monthly notifications to Institutions - {} rows".format("LIVE" if is_live else "TEST", len(csv_recs)))
    
    data_offset = 4         # January first data offset
    month_increment = 3     # Increment to get following month first data
    rec_type = "L" if is_live else "T"
    count = 0
    for row in csv_recs:
        org_name = row[0]
        if org_name == "Total":
            continue
        elif org_name == "Unique":
            ac_id = 0   # Special case = indicates Unique values
        else:
            ac_id = map_ac_org_name_to_id.get(org_name)
        if ac_id is None:
            write_error(report_name, row, "Org name not found")
            continue
        data_ix = data_offset
        for month in range(1, 13):
            rec = {"year_month_date": date(year, month, 1),
                   "type": rec_type,
                   "acc_id": ac_id, 
                   "metadata_only": int(row[data_ix]), 
                   "with_content": int(row[data_ix + 1])}
            data_ix += month_increment
            # Only insert record if non-zero data
            if rec["metadata_only"] or rec["with_content"]:
                stat_obj = mysql_dao.MonthlyInstitutionStatsDAO(rec)
                stat_obj.insert()
                count += 1
    print("  Num records inserted:", count)


def load_pub_harv_data(report_dir, report_name, pub_map_ac_org_name_to_id, harv_map_ac_org_name_to_id):
    report_path = "{}/{}".format(report_dir, report_name)

    print("\n* Migrating {}".format(report_name))

    # publisher report names are of form: "monthly_notifications_from_harvester_2018.csv" or
    # "monthly_notifications_from_publishers_2018.csv"
    is_pub = "publisher" in report_name
    year = int(report_name[-8:-4])

    csv_recs = read_report_csv(report_path)
    print("\nRead monthly {} spreadsheet - {} rows".format("PUBLISHER" if is_pub else "HARVESTER", len(csv_recs)))
    map_ac_org_name_to_id = pub_map_ac_org_name_to_id if is_pub else harv_map_ac_org_name_to_id
    dao_class = mysql_dao.MonthlyPublisherStatsDAO if is_pub else mysql_dao.MonthlyHarvesterStatsDAO
    data_offset = 1  # January first data offset
    month_increment = 2  # Increment to get following month first data
    count = 0
    for row in csv_recs:
        org_name = row[0]
        if org_name == "Total":
            continue
        else:
            ac_id = map_ac_org_name_to_id.get(org_name)
        if ac_id is None:
            write_error(report_name, row, "Org name not found")
            continue
        data_ix = data_offset
        for month in range(1, 13):
            recd_str = row[data_ix]
            matched_str = row[data_ix + 1]
            # Discard any decimal portion
            if '.' in recd_str:
                recd_str = recd_str.split('.', 1)[0]
            if '.' in matched_str:
                matched_str = matched_str.split('.', 1)[0]
            rec = {"year_month_date": date(year, month, 1),
                   "acc_id": ac_id,
                   "received": int(recd_str),
                   "matched": int(matched_str)}
            data_ix += month_increment
            # Only insert record if non-zero data
            if rec["received"] or rec["matched"]:
                stat_obj = dao_class(rec)
                stat_obj.insert()
                count += 1
    print("  Num records inserted:", count)


print("\nCreating Jper Reports Tables")
db = utils.SQLUtils(host=app.config["MYSQL_HOST"],
                    user=MYSQL_ADMIN or app.config["MYSQL_USER"],
                    password=MYSQL_ADMIN_PWD or app.config["MYSQL_PWD"],
                    db_name=app.config["MYSQL_DB"],
                    time_zone=app.config["MYSQL_TIMEZONE"])
db.drop_tables(JPER_REPORTS_TABLES.keys())
db.create_tables(JPER_REPORTS_TABLES)

print("\nGet account Ids and Org names")
ac_id_org_names_result = db.run_query("SELECT id, org_name FROM account ORDER BY 1;", fetch=True)
map_ac_org_name_to_id = { org_name: id for (id, org_name) in ac_id_org_names_result[0]}

print("\nGet harvester webservice Ids and Org names")
harv_id_names_result = db.run_query("SELECT id, name FROM h_webservice ORDER BY 1;", fetch=True)
map_ws_name_to_id = { name: id for (id, name) in harv_id_names_result[0]}


with app.app_context():
    # Load institution reports
    for csv_file in os.listdir(report_dir):
        if len(csv_file) > 30:
            load_institution_data(report_dir, csv_file, map_ac_org_name_to_id)
    # Load publisher/harvester reports
    for csv_file in os.listdir(pub_report_dir):
        if len(csv_file) > 30:
            load_pub_harv_data(pub_report_dir, csv_file, map_ac_org_name_to_id, map_ws_name_to_id)

err_file.close()
print("\n*** Script completed with {} errors ***".format(error_count))
if error_count:
    print("* Error file:", MIGRATION_ERRORS_FILE)
    print("* map_ac_org_name_to_id:\n", map_ac_org_name_to_id)
    print("* map_ws_name_to_id:\n", map_ws_name_to_id)
