#!/usr/bin/env python
"""
Script that
 1. Modifies `acc_repo_match_params table`, add column: `has_regex` & `had_regex`
 2. Set value of new `has_regex` & `had_regex` columns.
"""
import re
import os
from octopus.lib.dates import now_str
from octopus.core import initialise
from octopus.modules.mysql.utils import SQLUtils
from router.jper.app import app     # need to import app_decorator as other modules import it from here.
from router.shared.models.account import AccRepoMatchParams, AccRepoMatchParamsArchived

includes_regex = re.compile(r'[[|+?]')      # For testing if a name variant includes any REGEX
tbl = "acc_repo_match_params"
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
            DB_NAME = "jper_live"
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

    backup_tbl = f"{tbl}_r13_5_bak"
    archive_tbl = f"{tbl}_archived"
    backup_archive_tbl = f"{archive_tbl}_r13_5_bak"
    log_title(f"Make structural changes to '{tbl}' table")
    try:
        for sql, msg in [
            ("USE jper;", "Use 'jper' database"),
            # ("USE jper_live;", "Use 'jper_live' database"),
            # Match Params Tbl
            (f"CREATE TABLE {backup_tbl} LIKE {tbl};", f"Creating table '{backup_tbl}'"),
            (f"INSERT INTO {backup_tbl} SELECT * FROM {tbl};", f"Populating '{backup_tbl}'"),
            (f"""ALTER TABLE {tbl}
                ADD COLUMN `has_regex` TINYINT NULL DEFAULT NULL COMMENT 'Indicates whether Name Variants use REGEX.' AFTER `updated`,
                ADD COLUMN `had_regex` TINYINT NULL DEFAULT NULL COMMENT 'Parameters have included RegEx in the past, (even if they dont currently)' AFTER `has_regex`;
              """,
                f"Altering table '{tbl}' - adding `has_regex` & `had_regex` columns."),
            # Match Params Archive Tbl
            (f"CREATE TABLE {backup_archive_tbl} LIKE {archive_tbl};", f"Creating table '{backup_archive_tbl}'"),
            (f"INSERT INTO {backup_archive_tbl} SELECT * FROM {archive_tbl};", f"Populating '{backup_archive_tbl}'"),
            (f"""ALTER TABLE {archive_tbl}
                DROP COLUMN `created`,
                ADD COLUMN `has_regex` TINYINT NULL DEFAULT NULL COMMENT 'Indicates whether Name Variants use REGEX.' AFTER `updated`;
              """,
             f"Altering table '{tbl}' - dropping `created` column, adding `has_regex` column."),
        ]:
            admin_db.run_admin_query(sql, msg, commit=True)
    except Exception as e:
        abend(f"ERROR while {msg} (executing query {sql}) - {repr(e)}")


    ## Scroll through ALL Match Param Recs ##

    log_title(f"Scroll through ALL {tbl} & set new `has_regex` value where appropriate")

    match_param_scroller = AccRepoMatchParams.scroller_obj(scroll_num=95)
    with match_param_scroller:
        count = 0
        updated = 0
        for match_param_rec in match_param_scroller:
            count += 1
            update_rec = False
            log_msg = f"* Updating match_param rec ID {match_param_rec.id}"
            for name_var in match_param_rec.name_variants:
                if includes_regex.search(name_var):
                    log_msg += f" ~has_regex~ Name variant: '{name_var}'"
                    match_param_rec.has_regex = True
                    update_rec = True
                    break

            # Now check if any archived records include RegEx
            archive_has_regex = False
            archive_scroller = AccRepoMatchParamsArchived.scroller_obj(match_param_rec.id, pull_name="all_4_acc", scroll_num=96)
            with archive_scroller:
                for archive_rec in archive_scroller:
                    for name_var in archive_rec.name_variants:
                        if includes_regex.search(name_var):
                            archive_has_regex = True
                            archive_rec.has_regex = True
                            archive_rec.update()    # Update new has_regex field in archive record
                            write_log(f" * Updating archive rec PKID {archive_rec.pkid} ~has_regex~")
                            break
            if archive_has_regex:
                log_msg += f" ~~had_regex~~"
                match_param_rec.had_regex = True
                update_rec = True

            if update_rec:
                write_log(log_msg)
                match_param_rec.update()
                updated += 1

        write_log(f"*** Total {tbl} recs: {count} ***\n")

    log_title(f"Finished updating `{tbl}` - {updated} records updated out of {count} total recs.")

    write_log(f"Results written to file: {log_fname}")

    log_title("ALL DONE")
