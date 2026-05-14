#!/usr/bin/env python3
# """
# Script to do following:
#   - populate new MySQL database from old ES index
# """
from time import time
from octopus.lib.data import dictionary_get_dot_notation
from octopus.lib.dates import datetime_from_millisecs

from octopus.modules.shared.mysql_db_ddl import JPER_TABLES
from octopus.modules.mysql import utils
from octopus.modules.es.utils import ESWrapper, scroller
from octopus.modules.shared import mysql_dao
from router.jper.app import app

MIGRATION_ERRORS_FILE = "C:/Incoming/mysql_migration_errors_XXX-to-YYY.txt"
MYSQL_ADMIN = "admin"
MYSQL_ADMIN_PWD = "1#er1*<Ss%WE&0QxA]C_mNS[C=0XERBI"    # DEV Admin pwd
#MYSQL_ADMIN_PWD = "HuCfbmgVCBLURSMxOrDf"    # RDS TEST Admin pwd

PREVIEW = True  # Whether to preview settings (don't actually do anything) or make the changes
DEV = True      # Whether in development environment or not (if not, a Filesystem backup is automatically made)

# FOLLOWING 4 lines cause migration into "jper" database on TEST env
#app.config["MYSQL_HOST"] = "dr-oa-test-pubrouter.cewhgxkzt0vu.eu-west-1.rds.amazonaws.com"
app.config["MYSQL_USER"] = "admin"
app.config["MYSQL_PWD"] = MYSQL_ADMIN_PWD
app.config["MYSQL_DB"] = "jper"
# app.config["MYSQL_DB"] = "tmp"

# ES_HOST = "http://gateway:9200"  # Dev env
# ES_HOST = "http://gateway:9201"  # New Router Test env
# ES_HOST = "http://gateway:9203"  # Production
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

def create_jper_db():
    db = utils.SQLUtils(host=app.config["MYSQL_HOST"],
                        user=MYSQL_ADMIN or app.config["MYSQL_USER"],
                        password=MYSQL_ADMIN_PWD or app.config["MYSQL_PWD"],
                        time_zone=app.config["MYSQL_TIMEZONE"])
    db_name = app.config["MYSQL_DB"]
    db.drop_database(db_name)  # Drop database (if it exists)
    db.create_database(db_name)
    db.create_tables(JPER_TABLES)

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

def migrate_account_recs(es_wrapper, ws_dict):
    # Account index -> account table
    start_stuff("accounts")
    prep_insert(mysql_dao.AccOrgDAO)
    ac_dict = {}
    count = 0
    # Get all Accounts, sorted so that repository acs come last
    query = {
        "sort": {
            "role": "asc"
        },
        "query": {
            "match_all": {}
        }
    }
    status_map = {
        "off": 0,
        "succeeding": 1,
        "failing":2,
        "problem":3
    }
    # Sorted, so that recs are listed in this order: Admin, Publishers, Repositories
    for es_account in scroller(es_wrapper, "account", q=query, keepalive="5m"):
        # Move status from repository_data.status or publisher_data.status to status (at top level) AND convert from
        # String to Int:  'off' --> 0; 'Okay' --> 1; 'failing' --> 2; 'problem' --> 3
        # And adjust excluded provider ids to use NEW ids
        rename_field(es_account, "id", "uuid")   # Original id becomes uuid
        role = es_account.get("role")
        if role == "repository":
            repo_data = es_account["repository_data"]
            status = repo_data.get("status")
            if status is not None:
                del (repo_data["status"])

            matching_config = repo_data.get("matching_config")
            if matching_config:
                # Modify excluded provider ids
                excluded_provider_ids = matching_config.get("excluded_provider_ids")
                if excluded_provider_ids is not None:
                    new_excluded_provider_ids = []
                    for id in excluded_provider_ids:
                        # Is id a Publisher ac id?
                        new_id = ac_dict.get(id)
                        if new_id:
                            new_excluded_provider_ids.append("p{}".format(new_id))
                        else:
                            # Is id a Harvester ws id?
                            new_id = ws_dict.get(id)
                            if new_id:
                                new_excluded_provider_ids.append("h{}".format(new_id))
                    # Relocate excluded_provider_ids list from matching_config to higher level
                    repo_data["excluded_provider_ids"] = new_excluded_provider_ids if new_excluded_provider_ids else None
                    del matching_config["excluded_provider_ids"]
                # Remove created_date
                if "created_date" in matching_config:
                    del matching_config["created_date"]

            # Remove sword created_date:
            if dictionary_get_dot_notation(repo_data, "sword.created_date"):
                del repo_data["sword"]["created_date"]

        elif role == "publisher":
            status = dictionary_get_dot_notation(es_account, "publisher_data.status")
            if status is not None:
                del (es_account["publisher_data"]["status"])
        else:
            status = None
        es_account["status"] = status_map.get(status, 0)

        # Rename dict keys
        for new_key, old_key in [("created", "created_date"),
                                 ("updated", "last_updated")]:
            rename_field(es_account, old_key, new_key)

        # print("\n\n-------Account-", es_account)
        sql_account = mysql_dao.AccOrgDAO(es_account)
        data = sql_account.insert()
        ac_dict[data["uuid"]] = data["id"]
        count = show_progress("accounts", count)
    write_summary("accounts", count)
    return ac_dict


def migrate_h_websevice_recs(es_wrapper):
    # Harvester h_webservices index -> h_webservice table
    start_stuff("h_webservices")
    # prep_insert(mysql_dao.HarvWebServiceRecordDAO)

    ws_name_dict = {}
    ws_id_dict = {}
    count = 0
    for h_ws in scroller(es_wrapper, "webservice", safe_unpack=True, keepalive="5m"):
        linux_date_to_utc(h_ws, "end_date")
        bool_to_int(h_ws, "active")
        bool_to_int(h_ws, "publisher")
        # print("\n\n-------h_webservice-", h_ws)
        orig_ws_id = h_ws["id"]
        del h_ws["id"]
        sql_account = mysql_dao.HarvWebServiceRecordDAO(h_ws)
        data = sql_account.insert()
        ws_name_dict[data["name"]] = data["id"]
        ws_id_dict[orig_ws_id] = data["id"]
        count = show_progress("h_webservices", count)

    write_summary("h_webservices", count)
    return ws_name_dict, ws_id_dict


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


def migrate_pub_test(es_wrapper, ac_id_dict):
    # Jper pub_test index -> pub_test table -
    start_stuff("pub_test")
    prep_insert(mysql_dao.PubTestRecordDAO)
    query = {
        "sort": {
            "created_date": "asc"
        },
        "query": {
            "match_all": {}
        }
    }
    count = 0
    # Getting recs in Date ascending order
    for rec in scroller(es_wrapper, "pub_test", q=query, keepalive="5m"):
        del rec["id"]  # New Id will be automatically created
        del rec["last_updated"]  # New Id will be automatically created
        rename_field(rec, "created_date", "created")
        # replace UUID publisher_id by new publisher Id value
        rec["pub_id"] = ac_id_dict.get(rec["publisher_id"])
        del rec["publisher_id"]
        bool_to_int(rec, "valid")
        obj = mysql_dao.PubTestRecordDAO(rec)
        obj.insert()
        count = show_progress("pub_test", count)

    write_summary("pub_test", count)


def migrate_doi_regiser(es_wrapper, ac_id_dict):
    global error_count
    # Jper pub_test index -> pub_test table -
    start_stuff("doi_register")
    prep_insert(mysql_dao.DoiRegisterDAO)
    count = 0
    # Getting recs in Date ascending order
    for rec in scroller(es_wrapper, "doi_register", keepalive="15m"):
        rename_field(rec, "created_date", "created")
        rename_field(rec, "last_updated", "updated")
        new_repo_ids = [ ac_id_dict[repo_id] for repo_id in rec["repos"]]
        rec["repos"] = new_repo_ids
        # print("\n\n-------DOI_register-", rec)

        obj = mysql_dao.DoiRegisterDAO(rec)
        try:
            obj.insert()
        except Exception as e:
            write_error("DOI_register", rec, e)
        count = show_progress("doi_register", count)

    write_summary("doi_register", count)


def migrate_content_log(es_wrapper, ac_id_dict):
    global error_count
    # Jper contentlog index -> content_log table -
    start_stuff("content_log")
    print("--- NOT MIGRATING (info is currently useless) ---")


def migrate_identifiers(es_wrapper):
    global error_count
    # Jper contentlog index -> content_log table -
    start_stuff("org_identifiers")
    # prep_insert(mysql_dao.IdentifierDAO)
    count = 0
    # Getting recs in Date ascending order
    for rec in scroller(es_wrapper, "identifier", keepalive="5m"):
        rename_field(rec, "name_text", "name")
        obj = mysql_dao.IdentifierDAO(rec)
        try:
            obj.insert()
        except Exception as e:
            write_error("Org_identifier", rec, e)
        count = show_progress("org_identifiers", count)

    write_summary("org_identifiers", count)


def migrate_notifications(es_wrapper, ac_id_dict, ws_id_dict):
    global error_count
    # Jper notifications index -> notification table -
    start_stuff("notifications")
    prep_insert(mysql_dao.RoutedNotificationDAO)
    prep_insert(mysql_dao.UnroutedNotificationDAO)
    note_id_dict = {}      # Maps original notification ID to new ID

    query = {
        "sort": {
            "created_date": "asc"
        },
        "query": {
            "match_all": {}
        }
    }
    count = 0
    # Getting recs in Date ascending order (so oldest first)
    for rec in scroller(es_wrapper, "notification", q=query, keepalive="30m"):
        rename_field(rec, "created_date", "created")
        del rec["last_updated"]

        # Save current ID in "trans_uuid" column
        rename_field(rec, "id", "trans_uuid")

        # Type field becomes first character ('R' or 'U') of current type ("routed" or "unrouted)
        note_type = rec["type"][:1].upper()
        rec["type"] = note_type

        # Only Routed notifications have repositories field
        if note_type == "R":
            # Replace original repo-account rec UUID by new ID value
            new_repo_ids = [ ac_id_dict[repo_id] for repo_id in rec.get("repositories", [])]
            rec["repositories"] = new_repo_ids

        # Replace publisher ac UUID by new int ID
        rec["provider"]["id"] = ac_id_dict[rec["provider"]["id"]]

        # Replace harvester ws UUID by new int ID - this is stored in renamed provider field origin -> harv_id
        prov_harv_id = rec["provider"].get("origin")
        if prov_harv_id:
            rec["provider"]["harv_id"] = ws_id_dict[prov_harv_id]
            del rec["provider"]["origin"]

        # In provider-route, change "harvester" -> "harv"
        prov_route = rec["provider"].get("route")
        if prov_route and prov_route == "harvester":
            rec["provider"]["route"] = "harv"

        obj = mysql_dao.RoutedNotificationDAO(rec) if rec["type"] == "R" else mysql_dao.UnroutedNotificationDAO(rec)
        try:
            obj.insert()
            note_id_dict[rec["trans_uuid"]] = obj.id
            if new_repo_ids:
                mysql_dao.NotificationAccountDAO.start_transaction()
                # Create notification_account records for each repository.
                note_acc_dict = {"id_note": obj.id, "id_acc": None}
                for repo_id in new_repo_ids:
                    note_acc_dict["id_acc"] = repo_id
                    # Create notification_account record and insert it into database
                    mysql_dao.NotificationAccountDAO(note_acc_dict).insert(commit=False)
                mysql_dao.NotificationAccountDAO.commit()

        except Exception as e:
            write_error("Notification", rec, e)
        count = show_progress("notifications", count)

    write_summary("notifications", count)
    return note_id_dict


def migrate_match_prov(es_wrapper, ac_id_dict, note_id_dict):
    global error_count
    # Jper match_prov index -> match_provenance table -
    start_stuff("match provenance")
    prep_insert(mysql_dao.MatchProvenanceDAO)
    query = {
        "sort": {
            "created_date": "asc"
        },
        "query": {
            "match_all": {}
        }
    }
    count = 0
    # Getting recs in Date ascending order (so oldest first)
    for rec in scroller(es_wrapper, "match_prov", q=query, keepalive="15m"):
        del rec["id"]
        del rec["last_updated"]
        rename_field(rec, "created_date", "created")

        # Get the new notification integer ID
        note_id = note_id_dict.get(rec["notification"])
        if note_id is None:
            write_error("Match_provenance", rec, "Notification ID not found")
            continue
        rec["note_id"] = note_id
        del rec["notification"]

        # Get the new repository account ID
        rec["repo_id"] = ac_id_dict[rec["repository"]]
        del rec["repository"]

        obj = mysql_dao.MatchProvenanceDAO(rec)
        try:
            obj.insert()
        except Exception as e:
            write_error("Match_provenance", rec, e)
        count = show_progress("match_prov", count)

    write_summary("match_prov", count)


def migrate_pub_deposit(es_wrapper, ac_id_dict, note_id_dict):
    global error_count
    # Jper match_prov index -> match_provenance table -
    start_stuff("publisher deposit")
    prep_insert(mysql_dao.PubDepositRecordDAO)
    query = {
        "sort": {
            "created_date": "asc"
        },
        "query": {
            "match_all": {}
        }
    }
    count = 0
    # Getting recs in Date ascending order (so oldest first)
    for rec in scroller(es_wrapper, "pub_deposit", q=query, keepalive="30m"):
        del rec["id"]
        rename_field(rec, "created_date", "created")
        rename_field(rec, "last_updated", "updated")

        # Type --> single char (first char)
        rec["type"] = rec["type"][:1].upper()
        # Get the new notification integer ID
        orig_note_id = rec.get("notification_id")
        if orig_note_id:
            rec["note_id"] = note_id_dict.get(orig_note_id)
            del rec["notification_id"]
        else:
            rec["note_id"] = None

        # Get the new publisher account ID
        rec["pub_id"] = ac_id_dict[rec["publisher_id"]]
        del rec["publisher_id"]

        bool_to_int(rec, "matched")
        bool_to_int(rec, "successful")

        matched_live = rec.get("matched_live")
        if matched_live:
            rec["matched_live"] = 1 if matched_live else 0
        else:
            rec["matched_live"] = None

        err = rec.get("error")
        # Replace empty string by None (so will result in NULL in database)
        if not err:
            rec["error"] = None

        obj = mysql_dao.PubDepositRecordDAO(rec)
        try:
            obj.insert()
        except Exception as e:
            write_error("Pub_deposit", rec, e)
        count = show_progress("pub_deposit", count)

    write_summary("pub_deposit", count)

def migrate_sword_deposit(es_wrapper, ac_id_dict, note_id_dict):
    global error_count
    # Jper sword_deposit_record index -> sword_deposit table -
    start_stuff("SWORD deposit records")
    prep_insert(mysql_dao.SwordDepositRecordDAO)
    query = {
        "sort": {
            "created_date": "asc"
        },
        "query": {
            "match_all": {}
        }
    }

    status_map = {
        "none": None,
        "failed": 0,
        "deposited": 1,
    }

    count = 0
    # Getting recs in Date ascending order (so oldest first)
    for rec in scroller(es_wrapper, "sword_deposit_record", q=query, keepalive="15m"):
        del rec["id"]
        del rec["created_date"]
        del rec["last_updated"]

        # Get the new Repository account ID
        rec["repo_id"] = ac_id_dict.get(rec["repository"])
        del rec["repository"]

         # Get the new notification integer ID
        orig_note_id = rec.get("notification")
        if orig_note_id:
            rec["note_id"] = note_id_dict.get(orig_note_id)
            del rec["notification"]
        else:
            rec["note_id"] = None

        for field in ["error_message", "doi", "edit_iri"]:
            val = rec.get(field)
            # Replace empty string by None (so will result in NULL in database)
            if not val:
                rec[field] = None

        # Convert status strings to Int or None
        # "none" => None, "failed" => 0, "deposited" => 1
        for field in ["metadata_status", "content_status", "completed_status"]:
            rec[field] = status_map.get(rec.get(field))

        obj = mysql_dao.SwordDepositRecordDAO(rec)
        try:
            obj.insert()
        except Exception as e:
            write_error("Sword_deposit", rec, e)
        count = show_progress("sword_deposit", count)

    write_summary("sword_deposit", count)


try:
    with app.app_context():
        create_jper_db()
        jper_es_wrapper = ESWrapper(ES_HOST, "jper")
        migrate_identifiers(jper_es_wrapper)
        ws_name_dict, ws_id_dict = migrate_h_websevice_recs(ESWrapper(ES_HOST, "h_webservices"))
        ac_id_dict = migrate_account_recs(jper_es_wrapper, ws_id_dict)
        migrate_doi_regiser(jper_es_wrapper, ac_id_dict)
        migrate_pub_test(jper_es_wrapper, ac_id_dict)
        migrate_h_error_recs(ESWrapper(ES_HOST, "h_errors"), ws_name_dict)
        migrate_h_history_recs(ESWrapper(ES_HOST, "h_history"), ws_name_dict)
        note_id_dict = migrate_notifications(jper_es_wrapper, ac_id_dict, ws_id_dict)
        migrate_match_prov(jper_es_wrapper, ac_id_dict, note_id_dict)
        migrate_sword_deposit(jper_es_wrapper, ac_id_dict, note_id_dict)
        migrate_pub_deposit(jper_es_wrapper, ac_id_dict, note_id_dict)
except Exception as e:
    raise e

err_file.close()
print("\n*** Script completed with {} errors in {} seconds ***\n".format(error_count, int(time() - start_time)))
print("* Error file:", MIGRATION_ERRORS_FILE)

