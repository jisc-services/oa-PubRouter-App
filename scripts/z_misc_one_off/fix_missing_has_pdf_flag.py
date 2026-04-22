#!/usr/bin/env python
"""
FIX A BUG in which some notifications & existing doi_records did NOT have has-pdf indicator set,
when they should have done.

"""
import os
from octopus.core import initialise
from octopus.lib.dates import now_str
# import octopus.modules.mysql.dao as db
from octopus.modules.mysql.dao import TableDAO, DAO
from octopus.modules.mysql.utils import SQLUtils

from router.jper.app import app     # need to import app_decorator as other modules import it from here.
from router.shared.models.note import RoutedNotification
from router.shared.models.doi_register import DoiRegister


class ZNoteDAO(TableDAO):
    __table__ = "z_cum_notifications"

    __ignore_null__ = True  # When retrieving recs, don't create data dict entries where record fields (cols) are NULL

    # List of tuples for columns that are created/updated by MySQL
    __auto_sql_cols__ = []
    # List of tuples for columns that are created/updated automatically by this DAO
    __auto_dao_cols__ = []

    __extra_cols__ = [("id", None, None),
                      ("doi", None, None),  # Article DOI
                      ("prov_id", None, None),  # Id of Publisher provider (NOT harvester provider)
                      ("prov_harv_id", None, None),  # Id of Harvester provider
                      ("prov_route", None, None),
                      ("art_type", None, None),  # Article_type
                      ("category", None, None),
                      ("metrics_json", None, DAO.dict_to_from_json_str)  # Metrics structure
                      ]
    __json__ = []
    __pull_cursor_dict__ = {
        "pk": ("", ["id"], None),
        # ORDER BY clause direction (ASC or DESC) will be determined by the pull_all(order_by parameter)
        "all": ("", None, "id {}"),
        # Following queries are for use with bespoke_pull() function
        # Select max ID value (most recent record ID) from table
        "bspk_max_id": ("BSPK", f"SELECT MAX(id) FROM {__table__}", None),
        "bspk_min_id": ("BSPK", f"SELECT MIN(id) FROM {__table__}", None),
    }

    @classmethod
    def max_id(cls):
        """
        :return: Integer - Largest ID of record in table (i.e. Id of last record created)
        """
        rec_tuple_list = cls.bespoke_pull(pull_name="bspk_max_id")
        if rec_tuple_list:
            # Expect single array of results, with that array having 1 entry
            max_val = rec_tuple_list[0][0]
            return int(max_val) if max_val else None
        return None

    @classmethod
    def min_id(cls):
        """
        :return: Integer - Smallest ID of record in table (i.e. Id of first record created)
        """
        rec_tuple_list = cls.bespoke_pull(pull_name="bspk_min_id")
        if rec_tuple_list:
            # Expect single array of results, with that array having 1 entry
            min_val = rec_tuple_list[0][0]
            return int(min_val) if min_val else None
        return None

#
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
        print(f"\n** Running query - {msg} **\n\tQuery: \"{sql}\"", flush=True)

        result = self.admin_db.run_query(sql, commit=commit, fetch=fetch)
        if not fetch:
            print("\tResult: ", result, "\n", flush=True)



log_fname = os.path.join("/tmp", f"fix_missing_pdf_{now_str('%Y-%m-%d')}.txt")
log_file = open(log_fname, "w", encoding="utf-8")


def log_title(msg):
    write_log(f"\n***** {msg} *****\n")

def abend(msg):
    log_title(f"ABEND - {msg}")
    exit(1)

def write_log(s):
    print(s)
    log_file.write(s)


write_log(f"\nResults will be written to file: {log_fname}\n")

with app.app_context():

    initialise()
    env = app.config.get("OPERATING_ENV")
    admin_db = AdminDB(env)

    tbl = "doi_register"
    backup_tbl = "doi_register_bak"
    log_title(f"Changes to '{tbl}' ON UPDATE")
    try:
        for sql, msg in [
            (f"CREATE TABLE {backup_tbl} LIKE {tbl};", f"Creating table '{backup_tbl}'"),
            (f"INSERT INTO {backup_tbl} SELECT * FROM {tbl};", f"Populating '{backup_tbl}'"),
            (f"ALTER TABLE {tbl} CHANGE COLUMN `updated` `updated` DATETIME NOT NULL ;",
             f"Stop 'updated' column in '{tbl}' from changing automatically"),
        ]:
            admin_db.run_admin_query(sql, msg, commit=True)
    except Exception as e:
        abend(f"ERROR while {msg} (executing query {sql}) - {repr(e)}")

    first_z_id = ZNoteDAO.min_id()
    write_log(f"\nFirst notification in z_cum_notifications table: {first_z_id}")

    count = 0
    scroller = RoutedNotification.routed_scroller_obj(scroll_num=97)
    with scroller:
        for note in scroller:
            count += 1
            if (count % 1000) == 0:
                write_log(f"Processed {count} notifications")
            # If Publisher notification
            if note.provider_id:
                note_id = note.id
                if note.has_pdf:
                    write_log(f"\nFirst notification with has_pdf flag - ID: {note_id}, Created: {note.created}\n*** STOPPING PROCESSING notifications\n")
                    break   # EXIT LOOP

                # Update has_pdf indicator
                note.has_pdf = True     # Assume that flag SHOULD have been set
                dup_diffs_dict_list = note.dup_diffs
                metrics_dict = note.metrics
                metrics_dict["bit_field"] |= 4      # Set has-pdf field
                note.metrics = metrics_dict

                if dup_diffs_dict_list:
                    dup_diffs_dict = dup_diffs_dict_list[0]
                    dup_diffs_dict["curr_bits"] |= 4
                    try:
                        dup_diffs_dict = dup_diffs_dict_list[1]
                        dup_diffs_dict["curr_bits"] |= 4
                    except IndexError:
                        pass

                note.update()
                write_log(f"\nUpdated notification ID: {note_id}.")
                # Update temporary notification table
                if note_id >= first_z_id:
                    z_note_dict = ZNoteDAO.pull(note_id, for_update=True)
                    z_note_dict["metrics_json"]["bit_field"] |= 4       # Set metrics has-pdf flag
                    ZNoteDAO.update(z_note_dict)
                    write_log(f"\nUpdated z_cum_notifications.")

                # Update DOI register record
                doi_rec = DoiRegister.pull(note.article_doi, for_update=True)
                data_ = doi_rec.data
                try:
                    data_["cum"]["bit_field"] |= 4
                except KeyError:
                    data_["orig"]["bit_field"] |= 4
                doi_rec.update()
                write_log(f"\nUpdated doi_register ID: {doi_rec.id}.")

    log_title("Final changes to 'doi_register' table")
    try:
        for sql, msg in [
            (f"""ALTER TABLE {tbl} 
                CHANGE COLUMN `updated` `updated` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP ;""",
             f"Altering table  '{tbl}' to reset `updated` to change automatically.")
        ]:
            admin_db.run_admin_query(sql, msg, commit=True)
    except Exception as e:
        abend(f"ERROR while {msg} (executing query {sql}) - {repr(e)}")


write_log(f"\n**** {count} Notifications processed ****\n")
log_file.close()
