#!/usr/bin/env python3
# """
# Script to do following:
#   - populate new MySQL database - h_errors and h_history tables ONLY from old ES index
# """
from time import time
from octopus.lib.dates import datetime_from_millisecs

from octopus.modules.es.utils import ESWrapper, scroller
from octopus.modules.shared import mysql_dao
from router.jper.app import app
from router.shared.models.harvester import HarvesterWebserviceModel

MIGRATION_ERRORS_FILE = "/home/jenkins/mig/mysql_migration_errors_FIX.txt"
MYSQL_ADMIN = "admin"
MYSQL_ADMIN_PWD = "1#er1*<Ss%WE&0QxA]C_mNS[C=0XERBI"    # DEV Admin pwd
# MYSQL_ADMIN_PWD = "9Y5yfjSEEHvgtyVjwwRL"    # PROD Admin pwd

PREVIEW = False  # Whether to preview settings (don't actually do anything) or make the changes
DEV = False      # Whether in development environment or not (if not, a Filesystem backup is automatically made)

# FOLLOWING 4 lines cause migration into "jper" database on TEST env
#app.config["MYSQL_HOST"] = "dr-oa-test-pubrouter.cewhgxkzt0vu.eu-west-1.rds.amazonaws.com"
app.config["MYSQL_USER"] = "admin"
app.config["MYSQL_PWD"] = MYSQL_ADMIN_PWD
app.config["MYSQL_DB"] = "jper"

if not DEV:
    ES_HOST = "http://gateway:9200"

print("\n*** MIGRATE INDEX SCRIPT ***")
print("* Preview:\t", PREVIEW)
print("* Development env:\t", DEV)
print("* Error file:", MIGRATION_ERRORS_FILE)
if PREVIEW:
    exit(0)
error_count = 0
err_file = open(MIGRATION_ERRORS_FILE, "w", encoding="utf-8")
start_time = time()
migrate_start = time()

def start_stuff(desc):
    global migrate_start
    migrate_start = time()
    print("\n* Migrating {}".format(desc))

def write_error(table, rec, e):
    global error_count
    error_count += 1
    err_file.write("{}) {} error\n{}\n{}\n\n".format(error_count, table, rec, str(e)))

def write_summary(table, count):
    global migrate_start
    global start_time
    curr_time = time()
    msg = "records inserted: {} in {} secs.  (Total elapsed is {} secs).".format(
        count, int(curr_time - migrate_start), int(curr_time - start_time))
    print("{} - TOTAL {}".format(table, msg))
    err_file.write("\n {}: total {}\n\n---------------\n\n".format(table, msg))

def show_progress(table, count):
    global migrate_start
    global start_time
    curr_time = time()
    count += 1
    if count % 100 == 0:
        print(table, ": ", count, "records in", int(curr_time - migrate_start), "secs so far...  ", int(curr_time - start_time), "total secs")
    return count


def prep_insert(dao_cls):
    """
    This function alters the fundamental class configuration specifically for migration - it ensures that
    auto_sql columns, ARE INSERTED rather than the usual case of NOT inserting them (which normally causes SQL to
    always provide default values).  In particular this is intended to ensure that the migrated records have
    created and updated dates that match those from the original recs from ES.

    :param dao_cls:
    :return:
    """
    dao_cls._auto_pk_col, dao_cls._auto_pk_convert_fn = dao_cls._pk_col_if_set_automatically()
    dao_cls.__extra_cols__ = dao_cls.__auto_sql_cols__ + dao_cls.__extra_cols__
    dao_cls.__auto_sql_cols__ = []
    dao_cls._set_save_cols_names()
    sql = "INSERT INTO {} ({}) VALUES ({})".format(dao_cls.__table__,
                                                   ",".join(dao_cls._save_cols_names),
                                                   ",".join(["?"] * len(dao_cls._save_cols_names))
                                                   )
    dao_cls.prepare_cursor_obj("I", "insert", sql)


def rename_field(dic, curr_field, new_field):
    try:
        dic[new_field] = dic[curr_field]
        del dic[curr_field]
    except KeyError:
        dic[new_field] = None
        pass

def bool_to_int(dic, field):
    dic[field] = 1 if dic[field] else 0

def linux_date_to_utc(dic, field, format="%Y-%m-%d"):
    if dic.get(field):
        dic[field] = datetime_from_millisecs(dic[field]).strftime(format)


def create_ws_name_dict():
    # Harvester  h_webservice table

    count = 0
    ws_name_dict = {}
    for data in HarvesterWebserviceModel.get_webservices_dicts():
        ws_name_dict[data["name"]] = data["id"]

    write_summary("h_webservices", count)
    return ws_name_dict

def migrate_h_error_recs(es_wrapper, ws_dict):
    # Harvester h_errors index -> h_errors table
    # just LAST 100 errors
    start_stuff("h_errors (last 100)")
    prep_insert(mysql_dao.HarvErrorRecordDAO)
    query = {
        "sort": {
            "date": "desc"
        },
        "query": {
            "match_all": {}
        },
        "size": 100
    }
    h_recs = []
    for h_rec in scroller(es_wrapper, "errordoc", q=query, keepalive="5m"):
        if h_rec.get("name") is None:
            continue
        if h_rec.get("id"):
            del (h_rec["id"])
        doc = h_rec.get("document")
        if not doc:
            h_rec["document"] = None
        linux_date_to_utc(h_rec, "date", "%Y-%m-%dT%H:%M:%SZ")
        rename_field(h_rec, "date", "created")
        # Lookup the ID corresponding to ws name
        h_rec["ws_id"] = ws_dict[h_rec["name"]]
        del h_rec["name"]
        h_recs.append(h_rec)

    # Want to insert recs in date Ascending order so that ID order corresponds to date order
    h_recs.reverse()
    count = 0
    for h_rec in h_recs:
        # print("\n\n-------h_error-", h_rec)
        obj = mysql_dao.HarvErrorRecordDAO(h_rec)
        obj.insert()
        count = show_progress("h_errors", count)

    write_summary("h_errors", count)


def migrate_h_history_recs(es_wrapper, ws_dict):
    # Harvester h_errors index -> h_errors table -
    # just LAST 3 months data for 9 webservices ~830 recs
    start_stuff("h_history (last 3 months)")
    prep_insert(mysql_dao.HarvHistoryRecordDAO)
    query = {
        "sort": {
            "date": "desc"
        },
        "query": {
            "match_all": {}
        },
        "size": 830     # Approx 3 months data (9 harvesters x 92 days)
    }
    h_recs = []
    # Getting recs in Date descending order
    for h_rec in scroller(es_wrapper, "historic", q=query, keepalive="5m"):
        if h_rec.get("id"):
            del (h_rec["id"])

        linux_date_to_utc(h_rec, "date", "%Y-%m-%dT%H:%M:%SZ")
        rename_field(h_rec, "date", "created")

        linux_date_to_utc(h_rec, "start_date", "%Y-%m-%d")
        linux_date_to_utc(h_rec, "end_date", "%Y-%m-%d")

        # Lookup the webservice rec ID corresponding to ws name
        ws_id =  ws_dict.get(h_rec["name_ws"])
        if ws_id is None:
            print("!!! Skipping history rec: ", h_rec)
            continue
        h_rec["ws_id"] = ws_id
        del h_rec["name_ws"]

        rename_field(h_rec, "num_files_received", "num_received")
        rename_field(h_rec, "num_files_sent", "num_sent")
        # Just set num errors to 1 if there is at least one error
        h_rec["num_errors"] = 1 if h_rec["error"] else 0
        del h_rec["error"]
        h_recs.append(h_rec)

    # Want to insert recs in date Ascending order so that ID order corresponds to date order
    h_recs.reverse()
    count = 0
    for h_rec in h_recs:
        # print("\n\n-------h_error-", h_rec)
        obj = mysql_dao.HarvHistoryRecordDAO(h_rec)
        obj.insert()
        count = show_progress("h_history", count)

    write_summary("h_history", count)





try:
    with app.app_context():
        jper_es_wrapper = ESWrapper(ES_HOST, "jper")
        ws_name_dict = create_ws_name_dict()
        print(ws_name_dict)

        mysql_dao.HarvErrorRecordDAO.truncate_table()   # EMPTY h_errors
        migrate_h_error_recs(ESWrapper(ES_HOST, "h_errors"), ws_name_dict)

        mysql_dao.HarvHistoryRecordDAO.truncate_table() # EMPTY h_history
        migrate_h_history_recs(ESWrapper(ES_HOST, "h_history"), ws_name_dict)
except Exception as e:
    raise e

err_file.close()
print("\n*** Script completed with {} errors in {} seconds ***\n".format(error_count, int(time() - start_time)))
print("* Error file:", MIGRATION_ERRORS_FILE)

