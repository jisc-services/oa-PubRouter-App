#!/usr/bin/env python
"""
Script that
 1. Modifies doi_register table, add column: routed_live
 2. Set value of new routed_live column
"""
import os
from octopus.lib.dates import now_str
from octopus.core import initialise
from octopus.modules.mysql.utils import SQLUtils
from router.jper.app import app     # need to import app_decorator as other modules import it from here.
from router.shared.models.doi_register import DoiRegister
from router.shared.models.account import AccOrg

tbl = "doi_register"
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


write_log(f"\nResults will be written to file: {log_fname}\n")

with app.app_context():

    initialise()
    env = app.config.get("OPERATING_ENV")
    admin_db = AdminDB(env)

    backup_tbl = f"{tbl}_r13_4_bak"
    log_title(f"Make structural changes to '{tbl}' table")
    try:
        for sql, msg in [
            ("USE jper;", "Use 'jper' database"),
            (f"CREATE TABLE {backup_tbl} LIKE {tbl};", f"Creating table '{backup_tbl}'"),
            (f"INSERT INTO {backup_tbl} SELECT * FROM {tbl};", f"Populating '{backup_tbl}'"),
            (f"""ALTER TABLE {tbl} 
                ADD COLUMN `routed_live` TINYINT NULL DEFAULT NULL COMMENT 'Indicates DOI has been sent to at least 1 live repository.  Value 1 = DOI sent to at least 1 Live repository, 0 or NULL = DOI sent only to Test repos.' AFTER `has_pdf`,
                DROP INDEX `created_updated`,
                ADD INDEX `routedlive_created_updated` (`routed_live` ASC, `created` ASC, `updated` ASC) VISIBLE;
              """,
                f"Altering table '{tbl}' - adding `routed_live` column."),
        ]:
            admin_db.run_admin_query(sql, msg, commit=True)
    except Exception as e:
        abend(f"ERROR while {msg} (executing query {sql}) - {repr(e)}")


    ## Get IDs of all LIVE Repositories

    live_repo_acc_ids_dict = AccOrg.get_account_id_to_org_names_dict("R", live_test="L", close_cursor=True)

    ## Scroll through ALL temporary notification records & update DoiRegister records ##

    log_title(f"Scroll through ALL doi_records & set new `routed_live` value")

    doi_scroller = DoiRegister.scroller_obj(fetchmany_size=50, scroll_num=95)
    with doi_scroller:
        count = 0
        updated = 0
        for doi_rec in doi_scroller:
            count += 1
            for repo_id in doi_rec.repos:
                if live_repo_acc_ids_dict.get(repo_id) is not None:
                    doi_rec.routed_live = True
                    doi_rec.update(commit=False)
                    updated += 1
                    break
            if (count % 1000) == 0:
                write_log(f"Processed {count} DOI recs, updated {updated}.")
                doi_rec.commit()
        doi_rec.commit()
        write_log(f"*** Total DOI recs: {count} ***\n")

    log_title(f"Finished updating `{tbl}` - {updated} {tbl} records updated out of {count} total recs.")

    log_title("ALL DONE")
