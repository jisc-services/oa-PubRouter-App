#!/usr/bin/env python
"""
Script that
 1. Modifies doi_register table
 2. Populates the 2 new columns (`category` & `has_pdf`) from info extracted from bit-field.
"""
import os
from octopus.lib.dates import now_str
from octopus.core import initialise
from octopus.modules.mysql.dao import DAO, TableDAO, DICT
from octopus.modules.mysql.utils import SQLUtils
from router.jper.app import app     # need to import app_decorator as other modules import it from here.
from router.shared.models.doi_register import DoiRegister
from router.shared.models.note import RoutedNotification

log_fname = os.path.join("/tmp", f"update_modified_doi_register_{now_str('%Y-%m-%d')}.txt")
log_file = open(log_fname, "w", encoding="utf-8")

def write_log(s, flush=False):
    print(s, flush=flush)
    log_file.write(s + "\n")

def log_title(msg):
    write_log(f"\n***** {msg} *****\n")

def abend(msg):
    log_title(f"ABEND - {msg}")
    exit(1)


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
        "all": ("", None, None),
        # Following queries are for use with bespoke_pull() function
        # Select max ID value (most recent record ID) from table
        "bspk_max_id": ("BSPK", f"SELECT MAX(id) FROM {__table__}", None),
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


write_log(f"\nResults will be written to file: {log_fname}\n")

with app.app_context():

    initialise()
    env = app.config.get("OPERATING_ENV")
    admin_db = AdminDB(env)

    tbl = "doi_register"
    backup_tbl = "doi_register_r13_3_bak"
    log_title("Make structural changes to 'doi_register' table")
    try:
        for sql, msg in [
            ("USE jper;", "Use 'jper' database"),
            (f"CREATE TABLE {backup_tbl} LIKE {tbl};", f"Creating table '{backup_tbl}'"),
            (f"INSERT INTO {backup_tbl} SELECT * FROM {tbl};", f"Populating '{backup_tbl}'"),
            (f"""ALTER TABLE {tbl} 
                ADD COLUMN `category` CHAR(3) NULL DEFAULT NULL COMMENT 'Type of resource.  Value is between 1 and 3 characters. First character one of: J-journal, B-book, C-conference, R-report, P-pre-print, V-review, O-other. Second & third characters, if present, further refine the categorisation.' AFTER `updated`,
                ADD COLUMN `has_pdf` TINYINT NULL DEFAULT NULL COMMENT 'Indicates if text (e.g. PDF) supplied or not.  Value 1 = Full-text, NULL = Metadata only (no full text).' AFTER `category`,
                CHANGE COLUMN `updated` `updated` DATETIME NOT NULL COMMENT 'Value is always set deliberately, not automatically by MySQL.',
                ADD INDEX `created_updated` (`created` ASC, `updated` ASC) VISIBLE; """,
                f"Altering table '{tbl}' - adding 2 new columns 'category' & 'has_pdf', 'updated' changed: no longer set automatically"),
            # (f"ALTER TABLE {tbl} CHANGE COLUMN `updated` `updated` DATETIME NOT NULL COMMENT 'Value is always set deliberately, not automatically by MySQL.';",
            #  f"Stop 'updated' column in '{tbl}' from changing automatically"),
        ]:
            admin_db.run_admin_query(sql, msg, commit=True)
    except Exception as e:
        abend(f"ERROR while {msg} (executing query {sql}) - {repr(e)}")


    ## First set has_pdf & category fields for ALL records ##
    log_title("Set 'has_pdf' & 'category' fields for ALL `doi_register` records")

    doi_scroller = DoiRegister.scroller_obj(fetchmany_size=50, scroll_num=95)
    with doi_scroller:
        count = 0
        for doi_rec in doi_scroller:
            count += 1
            data_ = doi_rec.data
            try:
                bit_field = data_["cum"]["bit_field"]
            except KeyError:
                bit_field = data_["orig"]["bit_field"]
            # Has-PDF flag set
            if bit_field & 4:
                doi_rec.has_pdf = True
            # Have discovered error in setting has_pdf indicator, so setting to ON for all recs where we have had a publisher submission
            elif data_["best_rank"] < 3:       # 1: Publisher - normally have DPF, 2: EPMC - normally have URL to PDF
                doi_rec.has_pdf = True
                # Need to set has-pdf flag
                try:
                    data_["cum"]["bit_field"] |= 4
                except KeyError:
                    data_["orig"]["bit_field"] |= 4

            doi_rec.category = "JA"  # Journal Article (we have no way of determining what category really is)
            # print(doi_rec.data)
            doi_rec.update(commit=False)
            if (count % 1000) == 0:
                write_log(f"Processed {count} DOI recs")
                doi_rec.commit()
        doi_rec.commit()
        write_log(f"*** Total DOI recs: {count} ***\n")

    ## Update temporary notification table ##
    log_title("Update temporary notification table")

    NONE = "''"

    last_id = ZNoteDAO.max_id()
    write_log(f"\nLast notification ID processed: {last_id}")

    count = 0
    scroller = RoutedNotification.routed_scroller_obj(since_id=last_id, scroll_num=97)
    with scroller:
        for note in scroller:
            count += 1
            if (count % 1000) == 0:
                write_log(f"Processed {count}")
                ZNoteDAO.commit()
            raw_art_type = note.article_type
            # Publisher notification without an article type
            if note.provider_id is not None and not raw_art_type:
                cat = "JA"  # Default to Journal article
            else:
                cat = RoutedNotification.calc_category_from_article_type(raw_art_type or NONE)
            z_data = {
                "id": note.id,
                "doi": note.article_doi,  # Article DOI
                "prov_id": note.provider_id,  # Id of Publisher provider (NOT harvester provider)
                "prov_harv_id": note.provider_harv_id,  # Id of Harvester provider
                "prov_route": note.provider_route,
                "art_type": raw_art_type,  # Article_type
                "category": cat,
                "metrics_json": note.metrics
            }
            ZNoteDAO.insert(z_data, commit=False)

    if count:
        ZNoteDAO.commit()

    log_title(f"Total notifications recs added to temporary notifications table: {count}")

    ## Scroll through ALL temporary notification records & update DoiRegister records ##

    log_title(f"Scroll through ALL temporary notification records & update category value of `doi_register` records where needed")

    count = 0
    doi_count = 0
    z_scroller = ZNoteDAO.scroller_obj(fetchmany_size=50, rec_format=DICT, scroll_num=99)
    with z_scroller:
        for z_note_dict in z_scroller:
            count += 1
            if (count % 1000) == 0:
                write_log(f"Processed {count} temporary notification records")

            cat = z_note_dict["category"]   # Could occasionally be None
            if cat:
                doi = z_note_dict.get("doi")
                if doi:
                    doi_rec = DoiRegister.pull(doi, for_update=True)
                    if doi_rec:
                        curr_doi_cat = doi_rec.category
                        # different category and DOI rec has default category or is Publisher notification
                        if cat != curr_doi_cat and curr_doi_cat == "JA" or z_note_dict.get("prov_id"):
                            doi_count += 1
                            if (doi_count % 1000) == 0:
                                write_log(f"Updated {doi_count} DoiRegister records")
                                DoiRegister.commit()
                            doi_rec.category = cat
                            doi_rec.update(commit=False)
                    else:
                        write_log(f"!! DOI rec not found for DOI: {doi} !!")
    if doi_count:
        DoiRegister.commit()

    log_title(f"Finished updating `doi_register` - total of {doi_count} updates")

    # log_title("Final changes to 'doi_register' table")
    # try:
    #     for sql, msg in [
    #         (f"""ALTER TABLE {tbl}
    #             CHANGE COLUMN `updated` `updated` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP ;""",
    #          f"Altering table  '{tbl}' to reset `updated` to change automatically.")
    #     ]:
    #         admin_db.run_admin_query(sql, msg, commit=True)
    # except Exception as e:
    #     abend(f"ERROR while {msg} (executing query {sql}) - {repr(e)}")

    log_title("ALL DONE")
