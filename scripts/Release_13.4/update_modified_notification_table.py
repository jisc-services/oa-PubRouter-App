#!/usr/bin/env python
"""
Script that
 1. Modifies notification table, column: metrics_json --> metrics_val varchar(100)
 2. Recalculates contents of metrics_val column
"""
import os
from octopus.lib.dates import now_str
from octopus.core import initialise
from octopus.modules.mysql.utils import SQLUtils
from router.jper.app import app     # need to import app_decorator as other modules import it from here.
from router.shared.mysql_dao import RoutedNotificationDAO, DAO, DICT

tbl = "notification"
log_fname = os.path.join("/tmp", f"update_modify_{tbl}_{now_str('%Y-%m-%d')}.txt")
log_file = open(log_fname, "w", encoding="utf-8")


def write_log(s, flush=False):
    print(s, flush=flush)
    log_file.write(s + "\n")


def log_title(msg):
    write_log(f"\n***** {msg} *****\n")


def abend(msg):
    log_title(f"ABEND - {msg}")
    exit(1)


class AdminDB:

    def __init__(self, env=None):
        DB_NAME = "jper"
        DB_ADMIN_USER = "admin"
        if env == "development":
            DB_ADMIN_PWD = "1#er1*<Ss%WE&0QxA]C_mNS[C=0XERBI"
        elif env == "test":
            DB_ADMIN_PWD = "HuCfbmgVCBLURSMxOrDf"
        elif env == "staging":
            DB_ADMIN_PWD = "Nn6caDHHp1vKfEDmRDPI"
        elif env == "production":
            DB_ADMIN_PWD = "9Y5yfjSEEHvgtyVjwwRL"
        else:
            abend(f"UNEXPECTED Environment: '{env}' - cannot set MySQL admin password")

        MYSQL_HOST = app.config.get("MYSQL_HOST") or "localhost"
        self.admin_db = SQLUtils(host=MYSQL_HOST, user=DB_ADMIN_USER, password=DB_ADMIN_PWD, db_name=DB_NAME)
        log_title(f"Running in '{env}' environment")

    def run_admin_query(self, sql, msg, commit=False, fetch=False):
        write_log(f"\n** Running query - {msg} **\n\tQuery: \"{sql}\"", flush=True)

        result = self.admin_db.run_query(sql, commit=commit, fetch=fetch)
        if not fetch:
            write_log(f"\tResult: {result}\n", flush=True)


class OrigRoutedDAO(RoutedNotificationDAO):

    # IMPORTANT - Previous version of RoutedNotificationDAO, except that original "metrics_json" --> "metrics_val"
    __extra_cols__ = [("type", None, None),
                      ("analysis_date", None, DAO.convert_datetime),   # Sent to database as datetime object
                      ("doi", "metadata.article.doi", None),     # Article DOI
                      ("prov_id", "provider.id", None),     # Id of Publisher provider (NOT harvester provider)
                      ("prov_harv_id", "provider.harv_id", None),     # Id of Harvester provider
                      ("prov_agent", "provider.agent", None),
                      ("prov_route", "provider.route", None),
                      ("prov_rank", "provider.rank", None),
                      ("repositories", None, DAO.convert_int_list),     # repositories list is saved as string
                      ("pkg_format", "content.packaging_format", None),     # packaging format
                      ("links_json", "links", DAO.list_to_from_json_str),     # links list structure
                      ("metrics_val", "metrics", DAO.dict_to_from_json_str)     # Metrics structure
                      # **IMPORTANT** - if items are added/removed/moved in __extra_cols__ then you MUST review
                      # `bespoke_notes_part` which needs to specify all columns in the correct order AND the
                      # `format_rec(...)` function in `notifications_with_provenance(...)` func.
                      ]


write_log(f"\nResults will be written to file: {log_fname}\n")

with app.app_context():

    initialise()
    env = app.config.get("OPERATING_ENV")
    admin_db = AdminDB(env)

    backup_tbl = f"{tbl}_r13_4_bak"
    log_title("Make structural changes to 'notification' table")
    try:
        for sql, msg in [
            ("USE jper;", "Use 'jper' database"),
            (f"CREATE TABLE {backup_tbl} LIKE {tbl};", f"Creating table '{backup_tbl}'"),
            (f"INSERT INTO {backup_tbl} SELECT * FROM {tbl};", f"Populating '{backup_tbl}'"),
            (f"""ALTER TABLE {tbl} 
                CHANGE COLUMN `metrics_json` `metrics_val` VARCHAR(500) CHARACTER SET 'ascii' NULL DEFAULT NULL COMMENT 'Specially compressed notification metrics val dict. Will be NULL for UnroutedNotification.' ; """,
                f"Altering table '{tbl}' - changing `metrics_json` to `metrics_val`"),
        ]:
            admin_db.run_admin_query(sql, msg, commit=True)
    except Exception as e:
        abend(f"ERROR while {msg} (executing query {sql}) - {repr(e)}")


    ## Scroll through ALL temporary notification records & update DoiRegister records ##

    log_title(f"Scroll through ALL notification records & reformat them")

    count = 0
    special_routed_scroller = OrigRoutedDAO.scroller_obj(rec_format=DICT, order_by="asc", scroll_num=99)  #
    with special_routed_scroller:
        for note_dict in special_routed_scroller:
            count += 1
            metrics = note_dict.pop("metrics", None)
            if metrics:
                val = metrics.copy()
                new_metrics = {}
                new_metrics["h_count"] = val.pop("h_count")
                new_metrics["p_count"] = val.pop("p_count")
                new_metrics["val"] = val
                # print(new_metrics)
                note_dict["metrics"] = new_metrics
            RoutedNotificationDAO(note_dict).update(commit=False)
            if (count % 100) == 0:
                RoutedNotificationDAO.commit()
                if (count % 1000) == 0:
                    write_log(f"Processed {count} temporary notification records")
    if count:
        RoutedNotificationDAO.commit()

    log_title(f"Finished updating `{tbl}` - total of {count} updates")

    log_title("ALL DONE")
