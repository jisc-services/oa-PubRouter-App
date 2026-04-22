#!/usr/bin/env python3
#
# Script to do following:
#   - Create new records in 'acc_repo_match_params' table from records in 'account' table
#   - Modify account records to remove matching params

from router.jper.app import app     # need to import app_decorator as other modules import it from here.
from octopus.core import initialise
from octopus.modules.mysql.dao import DAO, DAOException
from octopus.modules.mysql.utils import SQLUtils
from router.shared.models.account import AccRepoMatchParams
from router.shared.mysql_db_ddl import JPER_TABLES



def abend(msg):
    print(f"\n***** ABEND - {msg} *****\n")
    exit(1)

class AdminDB:

    def __init__(self):
        DB_NAME = "jper"
        DB_ADMIN_USER = "admin"
        env = app.config.get("OPERATING_ENV")
        if env == "development":
            DB_ADMIN_PWD = "1#er1*<Ss%WE&0QxA]C_mNS[C=0XERBI"
        elif env == "test":
            DB_ADMIN_PWD = "HuCfbmgVCBLURSMxOrDf"
        elif env == "staging":
            DB_ADMIN_PWD = "Nn6caDHHp1vKfEDmRDPI"
        elif env == "production":
            DB_ADMIN_PWD = "9Y5yfjSEEHvgtyVjwwRL"
        else:
            abend("UNEXPECTED Environment: '{env}' - cannot set MySQL admin password")

        MYSQL_HOST = app.config.get("MYSQL_HOST") or "localhost"
        self.admin_db = SQLUtils(host=MYSQL_HOST, user=DB_ADMIN_USER, password=DB_ADMIN_PWD, db_name=DB_NAME)

    def run_admin_query(self, sql, msg, commit=False, fetch=False):
        print(f"\n** Running query - {msg} **\n\tQuery: \"{sql}\"", flush=True)

        result = self.admin_db.run_query(sql, commit=commit, fetch=fetch)
        if not fetch:
            print("\tResult: ", result, "\n", flush=True)


with app.app_context():

    initialise()

    admin_db = AdminDB()

    print("\n***** Creating 'account_original' table from 'account' table ****\n")
    for sql, msg in [("CREATE TABLE account_original LIKE account;", "Creating table 'account_original'"),
                     ("INSERT INTO account_original SELECT * FROM account;", "Populating 'account_original'"),
                     (JPER_TABLES["acc_repo_match_params"], "Creating table 'acc_repo_match_params'"),
                     (JPER_TABLES["acc_repo_match_params_archived"], "Creating table 'acc_repo_match_params_archived'"),
                     ]:
        admin_db.run_admin_query(sql, msg, commit=True)

    # uncompressed_json_recs = []

    ## Create NEW acc_repo_match_params records & Update original Repository account records ##
    # ac_rec_tuples, result_dict = DAO.run_query("SELECT id, json FROM account WHERE role = 'R';", fetch=True)
    ac_rec_tuples, result_dict = DAO.run_query("SELECT id, role, json FROM account;", fetch=True)
    for id, role, json_compressed in ac_rec_tuples:
        json_dict = DAO.dict_to_from_compressed_base64_string(json_compressed)
        if role == "R":
            repo_data = json_dict["repository_data"]
            matching_config = repo_data.pop("matching_config", None)
            if matching_config is None:
                continue

            # Remove max_pub_age from matching_config (if present)
            max_pub_age = matching_config.pop("max_pub_age", None)
            if max_pub_age is not None:
                # Relocate max_pub_age
                repo_data["max_pub_age"] = max_pub_age
            # Remove last_updated from matching_config (if present)
            last_updated = matching_config.pop("last_updated", None)

            # Create match params record
            match_params_obj = AccRepoMatchParams({"id": id, "matching_config": matching_config})
            match_params_obj.insert()

            compressed_json = DAO.dict_to_from_compressed_base64_string(json_dict, to_db=True)
            result = DAO.run_query(f"UPDATE account SET json = '{compressed_json}' WHERE id = {id};",
                                   commit=True, transaction=True)
            print(f"** Updated repository account compressed 'json' rec id: {id}.  Returned result: ", result, flush=True)
        # uncompressed_json_recs.append((id, json_dict))


    print("\n***** Altering 'account' table: changing size of 'json' column, adding 'jsonx' column ****\n")
    for sql, msg in [("ALTER TABLE `account` CHANGE COLUMN `json` `json` VARCHAR(30000) CHARACTER SET 'ascii' COLLATE 'ascii_bin' NULL DEFAULT NULL COMMENT ''; ", "Alter column 'account.json' to VARCHAR(30000)"),
                     ("ALTER TABLE `account` ADD COLUMN `jsonx` VARCHAR(10000) NULL AFTER `json`;", "Adding column 'account.jsonx'"),
                     ]:
        admin_db.run_admin_query(sql, msg, commit=True)

    ## Uncompress JSON in ALL account records
    print("\n***** Setting account.jsonx to uncompressed JSON ****\n")
    ac_rec_tuples, result_dict = DAO.run_query("SELECT id, json FROM account;", fetch=True)
    for id, json_compressed in ac_rec_tuples:
        json_dict = DAO.dict_to_from_compressed_base64_string(json_compressed)
        note = json_dict.get("note", "")
        if '"' in note:
            print(f" --- Double quote in Note for ID: {id} - replaced by **.")
            json_dict["note"] = note.replace('"', "**")     # Replace double quote by '**'
        json_string = DAO.dict_to_from_json_str(json_dict, to_db=True)
        if "'" in json_string:
            print(f" ---- Quote in JSON for ID: {id} - replaced by ^.")
            json_string = json_string.replace("'", "^")
        try:
            result = DAO.run_query(f"UPDATE account SET jsonx = '{json_string}' WHERE id = {id};",
                                   commit=True, transaction=True)
            print(f"** Updated 'account.jsonx' rec id: {id}.  Returned result: ", result, flush=True)
        except Exception as e:
            print(f"\n---PROBLEM ID {id}-------------------------\n{json_string}\n---------------------------\n", flush=True)
            print(repr(e), flush=True)
            exit(1)

    print("\n***** Altering 'account' table: Renaming 'json' -> 'json_orig', 'jsonx' -> 'json' ****\n")
    for sql, msg in [("ALTER TABLE `account` CHANGE COLUMN `json` `json_orig` VARCHAR(30000) CHARACTER SET 'ascii' COLLATE 'ascii_bin' NULL DEFAULT NULL;", "Rename column 'account.json' to 'account.json_orig'"),
                     ("ALTER TABLE `account` CHANGE COLUMN `jsonx` `json` VARCHAR(10000) NULL DEFAULT NULL;", "Rename column 'account.jsonx' to 'account.json'"),
                     ("UPDATE `account` SET json = REPLACE(json, '\r\n', ' +++ ');", "Replace \\r\\n")
                     ]:
        admin_db.run_admin_query(sql, msg, commit=True)

    print("\n***** ALL DONE *****\n")
