"""
This file specifies ALL the Classes used to access all the MySQL tables used by Router.

It also contains a mixin class with some specific helper functions that provide common functionality used in different
places.

THIS IS THE ONLY PLACE WHERE SQL QUERIES SHOULD BE DEFINED (except for release scripts in the /scripts directory).

In general there is one class per table (although notifications is a special case).

Each class defines the following:
* Table columns and their relationship to the corresponding Object data structure
* SQL queries used to Retrieve (pull) data (via cursors)
* Optionally SQL queries used for Insert, Update and Delete.  NOTE that the MySQL library octopus.modules.mysql.dao will
  by default automatically construct basic queries for Insert, Update & Delete, so only special cases need to be
  specified in these classes - BUT if a special case is specified here & the default is ALSO required, then
  the default must also be included in the class definition here.

IMPORTANT: Refer to the MySQL library octopus.modules.mysql.dao code to understand how the various class attributes are
used.

Author: Jisc
"""
from datetime import datetime
from octopus.lib.dates import any_to_datetime
# Note that some of imported values below although not used in this file are elsewhere imported from this file
from octopus.modules.mysql.dao import DAO, TableDAOMixin, RAW, DICT, WRAP, CONN_CLOSE, PURGE, DAOException

# These 2 snippets are used in a couple of places - so defining them here to avoid duplication. Status value 0 => Error
_sword_error_part = "CONCAT(IF(sd.metadata_status = 0, 'Metadata', IF(sd.content_status = 0, 'Content', 'Completion')), ' error: [ ', sd.note_id, IF(sd.content_status = 0 AND sd.edit_iri IS NOT NULL, CONCAT(' • ', sd.edit_iri), ''), ' • DOI: ', IFNULL(sd.doi, 'unknown'), ' ]. ', sd.error_message) AS err_msg"
_pub_error_part = "CONCAT('Filename: ', COALESCE(pd.name, 'unknown'), ' – ', pd.error) AS err_msg"


class ReportingHelperMixin:
    """
    Mixin class that provides functions used for Reporting purposes:
    * aggregate_over_time_period(...)
    * reformat_array_string(...)
    """
    @staticmethod
    def any_date_str_to_ymd_string(date_str, snippet, default_date_str=None):
        if date_str:
            # Convert any parsable date string to a datetime object
            new_date = any_to_datetime(date_str)
            if new_date is None:
                raise ValueError(f"Given {snippet} was not a date", date_str)
            return new_date.strftime("%Y-%m-%d")
        elif default_date_str:
            return default_date_str
        else:   # return today's date
            return datetime.today().strftime("%Y-%m-%d")

    @classmethod
    def aggregate_over_time_period(cls,
                                   *args,
                                   pull_name=None,
                                   to_date=None,
                                   from_date=None,
                                   page=None,
                                   page_size=None,
                                   do_count=True,
                                   rec_format=None,
                                   **kwargs):
        """
        Execute a query that counts number of records; and also returns an iterator to retrieve records that were counted.

        IMPORTANT: This function expects 2 Queries to be defined:
        1) Reporting query - returns multiple rows of data
        2) Count query - calculates Total number of rows that reporting query would return if NO limit set.
           The pull_name of this query must be of form `reporting-query-pull_name + "_count"`
           E.g. if (1) is given pull_name "agg_query" then (2) must have pull_name "agg_query_count"

        NOTE: the Names-of-files and Errors are Strings of text separated by '|' character - they can be split into lists
        :param args: Query parameters
        :param pull_name: String - Name of reporting query
        :param to_date: String - to-date
        :param from_date: String - from-date
        :param page: Int - page number in result set to return
        :param page_size: Int - number of results to return in this page of results
        :param do_count: Boolean - True: Calculate total count; False: Don't necessarily calculate total
        :param rec_format: Either an Integer - DICT, WRAP or RAW - determines how results should be returned -
                           as dicts, class-objects or raw data tuples;
                           OR a function with 1 parameter (raw record tuple) - that returns required thing

        :return: Tuple - (Count-of-total-recs, DAOScroller object for iterating over records.)
        """
        to_date_ymd = cls.any_date_str_to_ymd_string(to_date, "to_date")
        from_date_ymd = cls.any_date_str_to_ymd_string(from_date, "from_date", "2000-01-01")
        limit_offset = DAO.calc_limit_offset_param(page, page_size)
        # pull_name of count query is calculated by appending "_count" to reporting pull_name
        total_count = cls.count(*args, from_date_ymd, to_date_ymd, pull_name=f"{pull_name}_count") if do_count else None
        if rec_format is None:
            rec_format = RAW
        return total_count, cls.reusable_scroller_obj(
            *args, from_date_ymd, to_date_ymd, pull_name=pull_name, limit_offset=limit_offset, rec_format=rec_format, **kwargs)

    @staticmethod
    def reformat_array_string(string, replace_str=", ", default=""):
        """
        In an array string like "some|elements|separated|by|", replaces the "|" char with provided value.

        :param string:  String - of array elements separated by "|" char
        :param replace_str: String - which will be used to replace all "|" chars
        :param default: None or String - String to return if `string` is None
        :return: Reformatted string (or None)
        """
        return default if string is None else string.replace("|", replace_str)
        
        
class AccOrgDAO(TableDAOMixin):
    """
    DAO for Organisation Account
    """
    __table__ = "account"

    __ignore_null__ = True  # When retrieving recs, don't create data dict entries where record fields (cols) are NULL

    # List of tuples for columns that are created/updated by MySQL
    __auto_sql_cols__ = [("id", None, None),
                         ("created", None, DAO.convert_datetime),
                         ("updated", None, DAO.convert_datetime)
                         ]
    # List of tuples for columns that are created/updated automatically by this DAO
    __auto_dao_cols__ = [("uuid", None, DAO.make_uuid)]

    __extra_cols__ = [("deleted_date", None, DAO.reformat_datetime_str),  # deleted_date is CHAR(20) (not DATETIME)
                      ("api_key", None, None),
                      ("live_date", None, DAO.convert_datetime),   # Sent to database as datetime object
                      ("contact_email", None, None),
                      ("tech_contact_emails", None, DAO.convert_str_list),
                      ("role", None, None),         # role is one of ["A", "R", "P"] - aka Organisation TYPE
                      ("org_name", None, None),
                      ("status", None, None),    # status is one of [0, 1, 2, 3]
                      ("r_sword_collection", "repository_data.sword.collection", None),
                      ("r_repo_name", "repository_data.repository_info.name", DAO.empty_str_to_null),
                      ("r_excluded_providers", "repository_data.excluded_provider_ids", DAO.convert_str_list),
                      ("r_identifiers", "repository_data.identifiers", DAO.list_to_from_json_str),
                      ("p_in_test", "publisher_data.in_test", None),
                      ("p_test_start", "publisher_data.testing.start", None),
                      ]

    _repo_part = "deleted_date IS NULL AND role = 'R'"
    _pub_part = "deleted_date IS NULL AND role = 'P'"
    _bspk_probs_ac_select_part = "SELECT a.id AS acc_id, a.uuid AS acc_uuid, a.api_key, a.org_name, IF(a.live_date IS NULL, 'test', 'live') AS live_test, a.contact_email, a.tech_contact_emails, a.status"
    
    __pull_cursor_dict__ = {
        "pk": ("", ["id"], None),
        # "uuid": ("", ["uuid"], None),
        # "apikey": ("", ["api_key"], None),
        "uuid": ("WHERE", "deleted_date IS NULL AND uuid = ?", None),
        "apikey": ("WHERE", "deleted_date IS NULL AND api_key = ?", None),
        "contact": ("", ["contact_email"], None),
        "all": ("", None, None),
        # undeleted of type - Parameter is a composite string of allowed role values
        # E.g. 'R' only Repos, or 'RP' Repos & publishers; Order by clause may be specified by calling function
        "undeleted_type":
            ("WHERE", "deleted_date IS NULL AND INSTR(?, role)", "{}"),
        # Used only for GUI admin display
        "repo_live_test_status":
            # First param Live/Test repo indicator: 'LT' for either Live or Test repo; 'L' for Live repos; 'T' for Test repos
            # 1 --> returns rows where live_data IS NULL; 0 --> returns rows where live_date is NOT NULL
            ("WHERE", _repo_part + " AND INSTR(?, IF(live_date, 'L', 'T')) AND status BETWEEN ? AND ?", None),
        # Used in batch processing
        "repo_active":
            ("WHERE", _repo_part + " AND status > 0", None),
        "repo_active_live_or_test_like_orgname":
            # Param #1 should have value 1 (for Test repos) or 0 (for Live repos):
            #   1 --> returns rows where live_data IS NULL; 0 --> returns rows where live_date is either NULL or NOT NULL
            # Param #2 - Org-name string, may contain '%' wild-cards
            ("WHERE", _repo_part + " AND ISNULL(live_date) = ? AND status > 0 AND org_name LIKE ?", None),
        "sword_active":
            # Select repository accounts where r_sword_collection is a non-empty string (i.e. not NULL & not '')
            ("WHERE", _repo_part + " AND NULLIF(r_sword_collection, '') IS NOT NULL", None),
        # Takes 2 parameters: p-in-test String of acceptable values: '01' if any p_in_test value, otherwise '1' or '0'
        # p-test-start String of acceptable values: '01' if any p_test_start value , otherwise '1' or '0'
        "pub_autotest":
            ("WHERE", _pub_part + " AND INSTR(?, IF(p_in_test, '1', '0')) AND INSTR(?, IF(p_test_start, '1', '0'))", None),

        ## The following queries are for use with bespoke_pull() function

        "bspk_pub_test_ids":
            ("BSPK", "SELECT id FROM account WHERE " + _pub_part + " AND live_date IS NULL", None),
        # "bspk_acc_ids":
        #     ("BSPK", "SELECT id FROM account WHERE deleted_date IS NULL AND role = ?", None),
        "bspk_repo_ac_ids_providers":
            ("BSPK", "SELECT id, org_name, r_excluded_providers FROM account WHERE " + _repo_part, None),
        # Return id, org_name for all undeleted accounts of particular type (publisher &/or repository) with Live_date NULL or NOT NULL
        # 1st param one of ["P", "R", "PR"]."T" (Test repos), "L" (Live repos) or "TL" (Live & Test repos)
        # 2nd param should have value "T" (Test repos), "L" (Live repos) or "TL" (Live & Test repos)
        "bspk_org_names":
            ("BSPK", "SELECT id, org_name FROM account WHERE deleted_date IS NULL AND INSTR(?, role) AND INSTR(?, IF(live_date, 'L', 'T'))", None),
        # Return id, org_name, live_date for all undeleted, live, ON (status >0) accounts of particular type (publisher/repository)
        "bspk_org_names_sorted_livedate":
            ("BSPK", "SELECT id, org_name, live_date FROM account WHERE deleted_date IS NULL AND live_date IS NOT NULL AND status > 0 AND role = ? ", "live_date DESC"),
        # bspk_problems_... Lists: Acc-ID, acc-UUID. acc-API-key, acc-Org-name, live-or-test, acc-Contact-email, acc-Tech-Contact-emails, acc-status, metadata-error-note-id, Err-Date, Err-Msg (formatted), Err-ID, Err-emailed-indicator  ORDER BY Org-name, Err-ID
        # --IMPORTANT: if the number or order of columns changes then modify the SORT string accordingly - currently: "4, 12 DESC" (corresponding to Acc-Org-name and Err-ID)
        "bspk_problems_repository":
            ("BSPK",
             _bspk_probs_ac_select_part + ", IF(sd.metadata_status = 0, sd.note_id, 0), DATE(sd.deposit_date) AS err_date, " + _sword_error_part + ", sd.id AS err_id, sd.err_emailed FROM sword_deposit AS sd JOIN account AS a ON sd.repo_id = a.id WHERE a.role = 'R' AND a.status > ? AND sd.error_message is not NULL AND sd.deposit_date > SUBDATE(CURDATE(), ?)",
             "4, 12 DESC"),
        # Select publisher problems, for all publishers NOT switched off (status > 0)  ... ORDER BY Org-name, Error-ID
        "bspk_problems_publisher":
            ("BSPK",
             _bspk_probs_ac_select_part + ", 0, DATE(pd.created) AS err_date, " + _pub_error_part + ", pd.id AS err_id, pd.err_emailed FROM pub_deposit AS pd JOIN account AS a ON pd.pub_id = a.id WHERE a.role = 'P' AND a.status > ? AND pd.error is not NULL AND pd.created > SUBDATE(CURDATE(), ?)",
             "4, 12 DESC"),
        # Select undeleted organisations with count of their undeleted users, ORDER BY Count (col #6), Org-name (col #2)
        # Returns list of tuples [(acc-id, org-name, acc-uuid, org-role, org-status, user-count), ]
        "bspk_org_user_count":
            ("BSPK",
             "SELECT a.id, a.org_name, a.uuid, a.role, a.status, count(au.id) AS user_count FROM account a LEFT JOIN acc_user au ON a.id = au.acc_id AND au.deleted IS NULL WHERE a.deleted_date IS NULL AND INSTR(?, a.role) AND INSTR(?, IF(a.status = 0, 'F', 'O')) GROUP BY a.id ",
             "6, 2"),
    }

    __bespoke_update_insert_dict__ = {
        "update_repo_providers": "UPDATE account SET r_excluded_providers = ? WHERE id = ?"
    }


class AccUserDAO(TableDAOMixin):
    """
    DAO for Account-User (`acc_user` table)
    """
    __table__ = "acc_user"

    __ignore_null__ = True  # When retrieving recs, don't create data dict entries where record fields (cols) are NULL

    # List of tuples for columns that are created/updated by MySQL
    __auto_sql_cols__ = [("id", None, None),
                         ("created", None, DAO.convert_datetime),
                         ("updated", None, DAO.convert_datetime)
                         ]
    # List of tuples for columns that are created/updated automatically by this DAO
    __auto_dao_cols__ = [("uuid", None, DAO.make_uuid)]

    __extra_cols__ = [
                      ("last_success", None, DAO.reformat_datetime_str),  # last_success is CHAR(20) (not DATETIME)
                      ("last_failed", None, DAO.reformat_datetime_str),  # last_failed is CHAR(20) (not DATETIME)
                      ("deleted", None, DAO.reformat_datetime_str),  # deleted is CHAR(20) (not DATETIME)
                      ("acc_id", None, None),
                      ("username", None, None),
                      ("role_code", None, None),         # role is one of ["R", "S", "A", "J", "D")]
                      ("failed_login_count", None, None)
                      ]

    # Snippet setlects ALL 12 columns from acc_user and 19 columns from account in the ORDER in which they are defined above
    _select_user_org_cols_snippet = "SELECT au.id, au.created, au.updated, au.uuid, au.last_success, au.last_failed, au.deleted, au.acc_id, au.username, au.role_code, au.failed_login_count, au.json, a.id, a.created, a.updated, a.uuid, a.deleted_date, a.api_key, a.live_date, a.contact_email, a.tech_contact_emails, a.role, a.org_name, a.status, a.r_sword_collection, a.r_repo_name, a.r_excluded_providers, a.r_identifiers, a.p_in_test, a.p_test_start, a.json FROM acc_user au JOIN account a ON au.acc_id = a.id WHERE "
    __pull_cursor_dict__ = {
        "pk": ("", ["id"], None),
        # "uuid": ("", ["uuid"], None),
        "uuid": ("WHERE", "uuid = ? AND deleted IS NULL", None),
        # Select account VIA acc_user record
        "active_user": ("WHERE", "username = ? AND deleted IS NULL", None),
        "undeleted_of_type": ("WHERE", "INSTR(?, role_code) AND deleted IS NULL", None),
        "all_undeleted_4_acc": ("WHERE", "acc_id = ? AND deleted IS NULL", "{}"),
        # Takes 3 params: Account-ID, Role-code-string, Boolean include-deleted-recs
        "all_of_type_4_acc": ("WHERE", "acc_id = ? AND INSTR(?, role_code) AND IF(?, TRUE, ISNULL(deleted))", "{}"),

        ## The following queries are for use with bespoke_pull() function

        # Return combined User Account and its Parent organisation account data, via User Account username `acc_user.username`
        "bspk_user_n_org_ac_recs_by_username": ("BSPK", _select_user_org_cols_snippet + "au.username = ? AND au.deleted is NULL", None),
        # "bspk_user_n_org_ac_recs_by_username": ("BSPK", _select_user_org_cols_snippet + "au.username = ? ", None),

        # Return combined User Account and its Parent organisation account data, via User Account ID `acc_user.id`
        "bspk_user_n_org_ac_recs_by_user_id": ("BSPK", _select_user_org_cols_snippet + "au.id = ? AND au.deleted is NULL", None),

        # Return combined User Account and its Parent organisation account data, via User Account UUID `acc_user.uuid`
        # WILL return DELETED User accounts
        "bspk_user_n_org_ac_recs_by_user_uuid": ("BSPK", _select_user_org_cols_snippet + "au.uuid = ?", None),

        # Return combined User Account and its Parent organisation account data
        # The WHERE clause enables calling function to supply Character strings which retrieved column values are matched
        # against: Role-string (a string of required Org-Roles 'A', 'R', 'P'); Live-or-Test-indicator ('L' &/or 'T');
        # User-roles-string ('D', 'J', 'A', 'S', 'R'); Deleted-user-&/or-On-Off-Org-account ('D', 'O', 'F')
        "bspk_all_user_n_org_ac_recs": ("BSPK", _select_user_org_cols_snippet + "INSTR(?, a.role) AND INSTR(?, IF(a.live_date, 'L', 'T')) AND INSTR(?, au.role_code) AND INSTR(?, IF(au.deleted IS NOT NULL, 'D', IF(a.status = 0, 'F', 'O')))", None),

        # Return ALL acc_id, username (email addresses), role_code for users with specified role_codes for User Accounts associated with particular types of Organisation (usually 'R' &/or 'P') - sorted by acc_id, user-role_code
        "bspk_org_id_user_role_username_email_for_role_n_org_type": ("BSPK", "SELECT au.acc_id, au.role_code, au.username FROM acc_user au JOIN account a ON au.acc_id = a.id WHERE INSTR(?, au.role_code) AND INSTR(?, a.role) AND au.deleted is NULL", "acc_id ASC, role_code ASC"),

        # Return ALL acc_id, username (email addresses), role_code for users with specified role_codes for User Accounts associated with particular Organisation Account Ids - sorted by acc_id, user-role_code
        "bspk_org_id_user_role_username_email_for_role_n_org_ids": ("BSPK", "SELECT acc_id, role_code, username  FROM acc_user WHERE INSTR(?, role_code) AND FIND_IN_SET(CAST(acc_id AS CHAR),  ?) != 0 AND deleted is NULL", "acc_id ASC, role_code ASC"),
    }

    __bespoke_update_insert_dict__ = {
    }


class AccBulkEmailDAO(TableDAOMixin):
    """
    DAO for Bulk email table, which stores info about bulk emails sent to accounts.
    """
    __table__ = "acc_bulk_email"

    __ignore_null__ = False  # When retrieving recs, DO create data dict entries (set to None) where record fields (cols) are NULL

    # List of tuples for columns that are created/updated by MySQL
    __auto_sql_cols__ = [("id", None, None),
                         ]
    # List of tuples for columns that are created/updated automatically by this DAO
                        # Setting created datetime in DAO (rather than relying on setting by default in d/b
                        # because after inserting the record is immediately redisplayed; setting in DAO means
                        # that created date is immediately available without having to re-read the just saved record
    __auto_dao_cols__ = [("created", None, DAO.created_datetime)
                         ]

    __extra_cols__ = [("ac_type", None, None),     # Single char - Type of account:  "R": Repo, "P": Publisher, "A": All (both)
                      ("status", None, DAO.empty_str_to_null),     # Single char - Status: "H": Highlight; "D": Deleted; "R": Resolved/done
                      ("subject", None, None),
                      ("body", None, None)
                      ]

    __pull_cursor_dict__ = {
        "pk": ("", ["id"], None),
        # retrieve records from acc_bullk_email JOINED with acc_notes_emails JOINED with accounts where ac_type & status match the parameters that are passed, Highlighted recs listed first
        "bspk_emails": (
            "BSPK",
            "SELECT abe.id, abe.created, abe.ac_type, abe.status, abe.subject, abe.body, abe.json, GROUP_CONCAT(a.org_name ORDER BY 1 ASC SEPARATOR ', ') AS orgs FROM acc_bulk_email abe JOIN acc_notes_emails ane ON abe.id = ane.bulk_email_id JOIN account a ON a.id = ane.acc_id WHERE INSTR(?, COALESCE(abe.status, 'N')) AND INSTR(?, abe.ac_type) GROUP BY abe.id",
            "IF(abe.status = 'H', 1, 0) DESC, abe.id DESC"
        )
    }

    __bespoke_update_insert_dict__ = {
        "update_status": "UPDATE acc_bulk_email SET status = ? WHERE id = ?"
    }

    __delete_cursor_dict__ = {
        # "pk": ("", ["id"], None),     There is no need to delete individual records
        # Delete records with "Deleted" status that are older than specified date
        "deleted_status": ("WHERE", "status = 'D' AND created < ?", None)
    }


class AccNotesEmailsDAO(TableDAOMixin):
    """
    DAO for Account Notes / Emails table, which stores notes & emails related to an account.
    """
    __table__ = "acc_notes_emails"

    __ignore_null__ = False  # When retrieving recs, DO create data dict entries (set to None) where record fields (cols) are NULL

    # List of tuples for columns that are created/updated by MySQL
    __auto_sql_cols__ = [("id", None, None),
                         ]
    # List of tuples for columns that are created/updated automatically by this DAO
                        # Setting created datetime in DAO (rather than relying on setting by default in d/b
                        # because after inserting the record is immediately redisplayed; setting in DAO means
                        # that created date is immediately available without having to re-read the just saved record
    __auto_dao_cols__ = [("created", None, DAO.created_datetime)
                        ]

    __extra_cols__ = [("acc_id", None, None),   # FK to account record
                      ("type", None, None),     # Single char - Type of entry:  "E": Email; "N": Note; "T": To-do
                      ("status", None, DAO.empty_str_to_null),     # Single char - Status: "H": Highlight; "D": Deleted; "R": Resolved/done
                      ("bulk_email_id", None, None)     # THIS is NOT needed for normal record
                      ]

    __pull_cursor_dict__ = {
        "pk": ("", ["id"], None),
        # retrieve records from acc_notes_emails LEFT JOINED with acc_bulk_email where type & status match the parameters that are passed, Highlighted recs listed first, then ToDo recs
        # NULL status --> 'N'
        "bspk_notes_emails_status_for_ac": ("BSPK",
            "SELECT ane.id, ane.created, ane.acc_id, ane.type, ane.status, ane.bulk_email_id, ane.json, b.subject, b.body FROM acc_notes_emails AS ane LEFT JOIN acc_bulk_email AS b ON ane.bulk_email_id = b.id WHERE ane.acc_id = ? AND INSTR(?, COALESCE(ane.status, 'N')) AND INSTR(?, ane.type) ", "IF(ane.status = 'H', 2, IF(ane.type = 'T', 1, 0)) DESC, ane.id DESC")
    }

    __bespoke_update_insert_dict__ = {
        "update_status": "UPDATE acc_notes_emails SET status = ? WHERE id = ?",
        # Query to update bulk email records, where bulk_email_id matches specified parameter value
        "update_status_bulk_id": "UPDATE acc_notes_emails SET status = ? WHERE bulk_email_id = ?"
    }

    __delete_cursor_dict__ = {
        # "pk": ("", ["id"], None),     There is no need to delete individual records
        # Delete records with "Deleted" status that are older than specified date
        "deleted_status": ("WHERE", "status = 'D' AND created < ?", None)
    }


class AccRepoMatchParamsDAO(TableDAOMixin):
    """
    DAO for Repository account matching params table.
    """
    __table__ = "acc_repo_match_params"

    __ignore_null__ = False  # When retrieving recs, DO create data dict entries (set to None) where record fields (cols) are NULL

    # List of tuples for columns that are created/updated by MySQL
    __auto_sql_cols__ = [
                         ("created", None, DAO.convert_datetime),
                         ("updated", None, DAO.convert_datetime)
                        ]

    # List of tuples for columns that are created/updated automatically by this DAO
                        # Setting created datetime in DAO (rather than relying on setting by default in d/b
                        # because after inserting the record is immediately redisplayed; setting in DAO means
                        # that created date is immediately available without having to re-read the just saved record
    __auto_dao_cols__ = []

    __extra_cols__ = [("id", None, None),   # FK to account record
                      ("has_regex", None, None),     # Currently has RegEx
                      ("had_regex", None, None)      # Previously had RegEx
                      ]
    # Because matching_config can be huge (if lots of ORCIDS & Grant nums) need additional compression
    __json_func__ = DAO.dict_to_from_compressed_base64_string

    __pull_cursor_dict__ = {
        "pk": ("", ["id"], None),
        "all": ("", None, None),  # Select ALL records
        # Select ALL matching param records for ACTIVE Repo accounts
        "all_repo_active": ("WHERE", "id IN (SELECT id FROM account WHERE deleted_date IS NULL AND role = 'R' AND status > 0)", None),
        # Select ALL matching param records for UNDELETED Repo accounts
        "all_repo": ("WHERE", "id IN (SELECT id FROM account WHERE deleted_date IS NULL AND role = 'R')", None),
        # Select Org-Names, IDs, UUIDs, updated, Acc-status, Has-regex, Had-regex, Count-archived params
        "bspk_summary": ("BSPK", f"SELECT a.org_name, m.id, a.uuid, a.status, m.updated, COALESCE(m.has_regex, 0), COALESCE(m.had_regex, 0), (SELECT COUNT(*) FROM acc_repo_match_params_archived WHERE id = m.id) AS num_arch  FROM {__table__} m JOIN account a ON m.id = a.id WHERE a.deleted_date IS NULL AND a.status >= ?", "a.org_name ASC")
    }

    # __delete_cursor_dict__ = {
    #     # "pk": ("", ["id"], None),     There is no need to delete individual records
    # }


class AccRepoMatchParamsArchivedDAO(TableDAOMixin):
    """
    DAO for Repository account ARCHIVED matching params table.
    """
    __table__ = "acc_repo_match_params_archived"

    __ignore_null__ = False  # When retrieving recs, DO create data dict entries (set to None) where record fields (cols) are NULL

    # List of tuples for columns that are created/updated by MySQL
    __auto_sql_cols__ = [("pkid", None, None),
                         ("archived", None, None)       # This will be returned as datetime object
                        ]

    # List of tuples for columns that are created/updated automatically by this DAO
    __auto_dao_cols__ = []

    __extra_cols__ = [("id", None, None),   # FK to account record
                      ("updated", None, DAO.convert_datetime),
                      ("has_regex", None, None)     # Currently has RegEx
                      ]
    # Because matching_config can be huge (if lots of ORCIDS & Grant nums) need additional compression
    __json_func__ = DAO.dict_to_from_compressed_base64_string

    __pks__ = ["pkid"]  # Archive record does NOT use "id" as primary key

    __pull_cursor_dict__ = {
        "pk": ("", __pks__, None),
        "all_4_acc": ("", ["id"], "archived DESC"),  # Pull by account ID, most recent first
        "bspk_all_4_acc": ("BSPK", f"SELECT pkid, archived, COALESCE(has_regex, 0) FROM {__table__} WHERE id = ?", "pkid DESC")
    }

    __delete_cursor_dict__ = {
        # "pk": ("", ["id"], None),     There is no need to delete individual records
        "older_than": ("WHERE", "archived < ?", None)
    }


class ContentLogDAO(TableDAOMixin):
    """
    DAO for Content-Log which saves details in database of each content retrieval
    """
    __table__ = "content_log"

    __ignore_null__ = True  # When retrieving recs, don't create data dict entries where record fields (cols) are NULL

    # List of tuples for columns that are created/updated by MySQL
    __auto_sql_cols__ = [("id", None, None),
                         ("created", None, DAO.convert_datetime)
                         ]
    # List of tuples for columns that are created/updated automatically by this DAO
    __auto_dao_cols__ = []

    __extra_cols__ = [("note_id", None, None),
                      ("acc_id", None, None),
                      ("filename", None, None),
                      ("source", None, None)
                      ]
    # No JSON structure to store
    __json__ = []

    __delete_cursor_dict__ = {
        # "pk": ("", ["id"], None),     There is no need to delete individual records
        "older_than": ("WHERE", "created < ?", None)
    }


class CmsMgtCtlDAO(TableDAOMixin):
    __table__ = "cms_ctl"

    __ignore_null__ = True  # When retrieving recs, don't create data dict entries where record fields (cols) are NULL

    # List of tuples for columns that are created/updated by MySQL
    __auto_sql_cols__ = [("updated", None, DAO.convert_datetime)]
    __auto_dao_cols__ = []

    __extra_cols__ = [
        ("cms_type", None, None),
        ("sort_by", None, None),
        ("brief_desc", None, None),
    ]

    __pks__ = ["cms_type"]  # Record does NOT use "id" as primary key

    __pull_cursor_dict__ = {
        "pk": ("", __pks__, None),
        "all": ("", None, "cms_type"),
        "bspk_cms_types": ("BSPK", "SELECT cms_type, brief_desc FROM cms_ctl WHERE sort_by IS NOT NULL", "sort_by")
    }


class CmsHtmlDAO(TableDAOMixin):
    __table__ = "cms_html"

    __ignore_null__ = True  # When retrieving recs, don't create data dict entries where record fields (cols) are NULL

    # List of tuples for columns that are created/updated by MySQL
    __auto_sql_cols__ = [("id", None, None),
                         ("created", None, DAO.convert_datetime),
                         ("updated", None, DAO.convert_datetime)
                         ]
    __auto_dao_cols__ = []

    __extra_cols__ = [("status", None, DAO.empty_str_to_null),  # CHAR(1) - N: New (Draft); L: Live; D: Deleted; S: Superseded
                      ("cms_type", None, None),
                      ("sort_value", "fields.sort_value", None),
                      ]

    __pks__ = ["id"]

    __pull_cursor_dict__ = {
        "pk": ("", __pks__, None),
        "content_of_type": ("WHERE", "cms_type = ? AND INSTR(?, status)", "sort_value, id DESC"),
    }

    __delete_cursor_dict__ = {
        # "pk": ("", ["id"], None),     There is no need to delete individual records
        # Delete records with "Deleted" or "superseded" status that are older than specified date
        "deleted_status": ("WHERE", "status IN ('D', 'S') AND updated < ?", None)
    }


class DoiRegisterDAO(TableDAOMixin):
    """
    DAO for DOI register - which records all DOIs routed to at least one repository
    """
    __table__ = "doi_register"
    __ignore_null__ = True  # When retrieving recs, don't create data dict entries where record fields (cols) are NULL
    # List of tuples for columns that are created/updated by MySQL
    __auto_sql_cols__ = [("created", None, DAO.convert_datetime)]
    __auto_dao_cols__ = []
    # IMPORTANT: The `updated` field (below) is NOT set automatically (as it is in most other tables). Due to the way it
    # is used in 'bspk_simple_report' we don't want to risk the value changing if adhoc record updates are made via
    # scripts or SQL in future releases to support new functionality.
    __extra_cols__ = [("id", None, None),   # NB. `id` is a string DOI value
                      ("updated", None, DAO.convert_datetime),
                      ("category", None, None),
                      ("has_pdf", None, None),
                      ("routed_live", None, None)
                      ]

    __pks__ = ["id"]
    __pull_cursor_dict__ = {
        "pk": ("", __pks__, None),
        "all": ("", None, None),
        # count of items with full-text between start & end dates
        # Returns a row for each category code with 2 values: total_submissions, num_full_text.  The number of meta-data only = total - num_full_text.
        # Important: From-date, To-date are passed TWICE: [from, to, from, to] as are compared with both creted & updated dates
        "bspk_simple_report": ("BSPK", "SELECT SUBSTR(category, 1, 1) AS cat, COUNT(*) AS total, CAST(SUM(COALESCE(has_pdf, 0)) AS SIGNED) AS num_full_text FROM doi_register WHERE routed_live = 1 AND (DATE(created) BETWEEN ? AND ? OR DATE(updated) BETWEEN ? AND ?) GROUP BY cat", None),
    }

class IdentifierDAO(TableDAOMixin):
    """
    DAO for institution identifiers
    """
    __table__ = "org_identifiers"
    __ignore_null__ = True  # When retrieving recs, don't create data dict entries where record fields (cols) are NULL

    # List of tuples for columns that are created/updated by MySQL
    __auto_sql_cols__ = []
    # List of tuples for columns that are created/updated automatically by this DAO
    __auto_dao_cols__ = []

    __extra_cols__ = [("type", None, None),
                      ("value", None, None),
                      ("name", None, None)]
    # No JSON structure to store
    __json__ = []

    __pks__ = ["type", "value"]    # Primary keys: composite key

    __pull_cursor_dict__ = {
        "pk": ("AND", __pks__, None),
        "all": ("", None, "type DESC, name ASC "),
        "all_of_type": ("", ["type"], None),                  # Select ALL records of particular type
        # Following queries are for use with bespoke_pull() function
        # Select ALL records from org_identifiers ORDER BY name DESC
        "all_of_type_wildcard": ("WHERE", "type LIKE ? AND name LIKE ?", "name DESC"),
    }

    __delete_cursor_dict__ = {
        # "pk": ("", ["id"], None),     There is no need to delete individual records
        "all_of_type": ("", ["type"], None)
    }


class JobDAO(TableDAOMixin):
    """
    DAO for job records. Note that all dates specified in __auto_sql_cols__ and __extra_cols__ are stored in Python
    data-structures as datetime objects (this contrasts with most other DAO objects, where they are stored as strings.
    """
    __table__ = "job"
    # __ignore_null__ = True  # When retrieving recs, don't create data dict entries where record fields (cols) are NULL

    # List of tuples for columns that are created/updated by MySQL
    __auto_sql_cols__ = [
        ("id", None, None),
        ("created", None, DAO.set_utc_timezone),
    ]
    # List of tuples for columns that are created/updated automatically by this DAO
    __auto_dao_cols__ = []

    __extra_cols__ = [
        ("server_prog", None, None),
        ("status", None, None),
        ("priority", None, None),
        ("end_time", None, DAO.set_utc_timezone),
        ("next_start", None, DAO.set_utc_timezone),
        ("last_run", None, DAO.set_utc_timezone),
        ("periodicity", None, DAO.convert_timedelta),
    ]

    __pks__ = ["id"]            # Primary key(s) - allows for composite keys

    __pull_cursor_dict__ = {
        "pk": ("", __pks__, None),
        # Retrieve all jobs except those with priority of `NEVER`. When sorting results, NULL next_start are listed last
        "all_active_sorted": ("WHERE", "priority < 99", "priority ASC, COALESCE(next_start, '9999-09-09') ASC"),
        "all_sorted_priority": ("", None, "priority ASC, COALESCE(next_start, '9999-09-09') ASC"),
        "all_sorted_nextstart": ("", None, "COALESCE(next_start, '9999-09-09') ASC, priority ASC"),
    }

    __delete_cursor_dict__ = {
        "pk": ("", __pks__, None),
        "all_4_server_prog": ("", ["server_prog"], None)
    }


class MatchProvenanceDAO(TableDAOMixin):
    """
    DAO for MatchProvenance
    """
    __table__ = "match_provenance"
    __ignore_null__ = True  # When retrieving recs, don't create data dict entries where record fields (cols) are NULL

    # List of tuples for columns that are created/updated by MySQL
    __auto_sql_cols__ = [("created", None, DAO.convert_datetime)]
    # List of tuples for columns that are created/updated automatically by this DAO
    __auto_dao_cols__ = []

    # **IMPORTANT** - if items are added/removed/moved in __extra_cols__ then you MUST review `bespoke_notes_part`
    # which needs to specify all columns in the correct order
    __extra_cols__ = [("note_id", None, None),
                      ("repo_id", None, None)]
    __pks__ = ["note_id", "repo_id"]            # Primary key(s) - allows for composite keys

    __pull_cursor_dict__ = {
        "pk": ("AND", __pks__, None),
        "all": ("", None, "id DESC"),
        "all_by_note_id": ("", ["note_id"], "created ASC"),
        "matching_note_ids": ("", ["note_id"], "created ASC"),
    }

    __delete_cursor_dict__ = {
        # "pk": ("", ["id"], None),     There is no need to delete individual records
        "older_than": ("WHERE", "created < ?", None)
    }


class HarvestedUnroutedNotificationDAO(TableDAOMixin):
    """
    Class for Harvested Unrouted notifications.
    *** It is IDENTICAL to UnroutedNotificationDAO - EXCEPT the data is stored in a different table ***
    """
    __table__ = "harvested_unrouted"
    __ignore_null__ = True  # When retrieving recs, don't create data dict entries where record fields (cols) are NULL

    # List of tuples for columns that are created/updated by MySQL
    __auto_sql_cols__ = [("id", None, None),
                         # created datetime values returned by MySQL are converted to UTC timestamp Strings
                         ("created", None, DAO.convert_datetime)
                         ]
    # List of tuples for columns that are created/updated automatically by this DAO
    __auto_dao_cols__ = []

    __extra_cols__ = []

    __pull_cursor_dict__ = {
        "pk": ("", ["id"], None),
        # ORDER BY clause direction (ASC or DESC) will be determined by the pull_all(order_by parameter)
        "all": ("", None, "id {}"),
        # Following queries are for use with bespoke_pull() function
        # Select max ID value (most recent record ID) from table
        "bspk_max_id": ("BSPK", "SELECT MAX(id) FROM harvested_unrouted", None),
    }

    __delete_cursor_dict__ = {
        "pk": ("", ["id"], None),
        "del_upto_id": ("WHERE", "id <= ?", None)
    }


# metrics_val_dict_to_from_string was ORIGINALLY declared as @staticmethod within class NotificationDAO, but execution
# failed with `TypeError: 'staticmethod' object is not callable` error, hence moved it outside the class
def metrics_val_dict_to_from_string(val, to_db=False):
    """
    Convert the metrics.val dict to or from a minimised string format with values in PARTICULAR order
    sepearated by "|" - a bit_field value, followed by COUNTS of attributes:
    bit_field | authors | orcids | funders | funder-ids | grants | licenses | structured-affiliations | affiliation-ids.

    NOTE that the PRIMARY REASON for storing the `metrics.val` dict in this way (rather than as JSON) is to facilitate
    the database query for checking publisher duplicate submissions (see "bspk_duplicate_submissions" query in
    PubDepositRecordDAO).

    Metrics val dict
    "val": {
        "bit_field": Bitfield - Indicating presence of particular Metadata fields/values.
        "n_auth": Number of authors,
        "n_orcid": Number of authors with ORCIDs,
        "n_fund": Number of funders,
        "n_fund_id": PNumber of funder IDs,
        "n_grant": Number of grants,
        "n_lic": Number of licences,
        "n_struct_aff": Number of structured author affiliations,
        "n_aff_ids": Number of structured author affiliations with Org Ids,
        "n_cont": Number of non-author contributors,
        "n_hist": Number of history dates,
    }
    :param val: dict or string (depending on whether insert to db record or extracting from db record
    :param to_db: Boolean - True: Convert dict to special string; False: convert special string to dict

    """
    # We need data to be packaged in a particular order - ANY NEW KEYS MUST BE ADDED TO END OF LIST
    ordered_keys = [
        "bit_field", "n_auth", "n_orcid", "n_fund", "n_fund_id", "n_grant", "n_lic", "n_struct_aff", "n_aff_ids", "n_cont", "n_hist"
    ]

    def _dict_to_special_string(dic):
        """
        Compress metrics.val dict into a String with contents separated by '|' in particular order:
            "bit_field|n_auth|n_orcid|n_fund|n_fund_id|n_grant|n_lic|n_struct_aff|n_aff_ids|n_cont|n_hist"
        :param dic: Dict to convert to special string
        :return: String of dict values separated by '|'
        """
        str_list = []
        for k in ordered_keys:
            str_list.append(str(dic.get(k, "")))
        return "|".join(str_list)

    def _special_string_to_dict(string):
        """
        Convert String of dict values in particular order separated by '|' back into the metrics.val dict.
        :param string: String like "bit_field|n_auth|n_orcid|n_fund|n_fund_id|n_grant|n_lic|n_struct_aff|n_aff_ids|n_cont|n_hist"
        :return: dict
        """
        dic = {}
        data_list = string.split("|")
        for x, k in enumerate(ordered_keys):
            try:
                dic[k] = int(data_list[x])
            except IndexError:
                break
        return dic

    if to_db:
        return _dict_to_special_string(val) if val else None
    else:
        return _special_string_to_dict(val) if val else {}


class NotificationDAO(TableDAOMixin):
    """
    Parent class for Notifications (both Routed and Unrouted) which are stored in "notification" table.
    """
    __table__ = "notification"
    __ignore_null__ = True  # When retrieving recs, don't create data dict entries where record fields (cols) are NULL

    # List of tuples for columns that are created/updated by MySQL
    __auto_sql_cols__ = [("id", None, None),
                         # created datetime values returned by MySQL are converted to UTC timestamp Strings
                         ("created", None, DAO.convert_datetime)
                         ]
    # List of tuples for columns that are created/updated automatically by this DAO
    __auto_dao_cols__ = []

    # **IMPORTANT** - if items are added/removed/moved in __extra_cols__ then you MUST review `bespoke_notes_part`
    # which needs to specify all columns in the correct order AND the `format_rec(...)` function in
    # `notifications_with_provenance(...)` func.
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
                      ("metrics_val", "metrics.val", metrics_val_dict_to_from_string)  # Metrics.val structure
                      # **IMPORTANT** - if items are added/removed/moved in __extra_cols__ then you MUST review
                      # `bespoke_notes_part` which needs to specify all columns in the correct order AND the
                      # `format_rec(...)` function in `notifications_with_provenance(...)` func.
                      ]

    __pull_cursor_dict__ = {
        # IMPORTANT - used for pulling EITHER Routed OR Unrouted
        "pk": ("", ["id"], None),
        "pk_type": ("", ["id"], None),          # This special case of pk_type deliberately does NOT specify the type
        "all": ("", None, None),  # Select ALL records
    }

    __delete_cursor_dict__ = {
        "pk": ("", ["id"], None),
        # This will delete notification records older than date parameter PLUS any associated notification_account records.
        # LEFT JOIN ensures that any unrouted notfications (without corresponding notification_account recs) are deleted
        # Query uses `analysis_date` as it is indexed, unlike `created`
        "older_than": ("BSPK", "DELETE n, na FROM notification AS n LEFT JOIN notification_account AS na ON n.id = na.id_note WHERE DATE(n.analysis_date) < ?", None)
    }

    ### Notification specific code follows ###
    __type__ = None

    @classmethod
    def pull(cls, *pull_key_vals, pull_name="pk", for_update=False, wrap=True, raise_if_none=False):
        if pull_name == "pk":
            pull_name = "pk_type"

            if cls.__type__:
                # Here we automatically add the appropriate `type` indicator character ("U" or "R")
                pull_key_vals = pull_key_vals + (cls.__type__, )
        rec_dict = super().pull(*pull_key_vals, pull_name=pull_name, for_update=for_update, wrap=False, raise_if_none=raise_if_none)
        return cls(rec_dict) if wrap and rec_dict is not None else rec_dict


class UnroutedNotificationDAO(NotificationDAO):
    """
    Class for Unrouted notifications.
    *** Uses only a sub-set of columns in notification table to AVOID creating unnecessary Index entries ***
    UnroutedNotification extracts ONLY "type" and "trans_uuid" from the JSON when it is inserted or updated in database.
    (At the point where an unrouted notification is converted to a RoutedNotification, the update() function will extract
     from JSON & populate the full set of columns in notification record).
    """
    __type__ = "U"  # Unrouted

    __extra_cols__ = [("type", None, None),
                      # ("analysis_date", None, None),      # Not set for Unrouted notifications
                      # ("doi", "metadata.article.doi", None),     # Article DOI
                      # ("prov_id", "provider.id", None),     # Id of Publisher provider (NOT harvester provider)
                      # ("prov_harv_id", "provider.harv_id", None),     # Id of Harvester provider
                      # ("prov_agent", "provider.agent", None),
                      # ("prov_route", "provider.route", None),
                      # ("prov_rank", "provider.rank", None),
                      # ("repositories", None, DAO.convert_str_list),     # Not set for Unrouted notifications
                      # ("pkg_format", "content.packaging_format", None),     # packaging format
                      # ("links_json", "links", DAO.list_to_from_json_str),     # links list structure
                      # ("metrics_val", "metrics.val", metrics_val_dict_to_from_string)  # Metrics.val structure
                      ]

    __pull_cursor_dict__ = {
        "pk": ("", ["id"], None),   # This is required in case insert() or update() are called with reload=True
        # SPECIAL version of "pk" - include the "type" column
        "pk_type": ("AND", ["id", "type"], None),  # The `type` param value is automatically added by NotificationDAO.pull()
        # ORDER BY clause direction (ASC or DESC) will be determined by the pull_all(order_by parameter)
        "all": ("WHERE", "type = 'U'", "id {}"),
    }

    __delete_cursor_dict__ = {
        "pk": ("", ["id"], None),
        "del_upto_id": ("WHERE", "type = 'U' AND id <= ?", None)
    }

    # These variables need initialising here because NotificationDAO (which this class inherits from) can be called
    # independently, which will set these values, which we don't want to inherit here.
    _all_cols = None
    _save_cols_names = None


class RoutedNotificationDAO(NotificationDAO):
    """
    Class for Routed notifications.
    Uses full set of columns of notification table (which it inherits from NotificationDAO).
    """
    __type__ = "R"  # Routed

    # __extra_cols__ is SAME AS NotificationDAO

    _select_all_4pub_ac_part = "SELECT {} FROM notification AS n WHERE n.prov_id = ? AND "
    _select_all_4rac_part = "SELECT {} FROM notification AS n INNER JOIN notification_account AS na ON n.id = na.id_note WHERE na.id_acc = ? AND "

    # IMPORTANT: In bespoke_notes_part the column order MUST match the order of entries in the __auto_sql_cols__, __auto_dao_cols__, __extra_cols__ lists defined for BOTH NotificationDAO and MatchProvenanceDAO
    _bspk_notes_matchprov_part = "SELECT n.id, n.created, n.type, n.analysis_date, n.doi, n.prov_id, n.prov_harv_id, n.prov_agent, n.prov_route, n.prov_rank, n.repositories, n.pkg_format, n.links_json, n.metrics_val,  n.json, mp.created, mp.note_id, mp.repo_id, mp.json FROM notification AS n INNER JOIN notification_account AS na ON n.id = na.id_note INNER JOIN match_provenance AS mp ON mp.note_id = n.id AND mp.repo_id = na.id_acc WHERE na.id_acc = ? AND "
    
    __pull_cursor_dict__ = {
        "pk": ("", ["id"], None),   # This is required in case insert() or update() are called with reload=True
        # SPECIAL version of "pk" based on "id" & "type" columns
        "pk_type": ("AND", ["id", "type"], None),  # The `type` param value is automatically added by NotificationDAO.pull()
        # ORDER BY clause direction (ASC or DESC) will be determined by the pull_all(order_by parameter)
        "all": ("WHERE", "type = 'R'", "id {}"),
        "all_since_id": ("WHERE", "type = 'R' AND id > ?", "id {}"),
        # Don't need to check for type = 'R' because only routed notifications have analysis date set (and it is indexed)
        "all_since_date": ("WHERE", "DATE(analysis_date) >= ?", "id {}"),
        "all_on_date": ("WHERE", "DATE(analysis_date) = ?", "id {}"),
        # Here, although doi is only set for routed notifications we ARE checking type = 'R' because type is indexed, but doi is NOT
        "all_like_doi": ("WHERE", "type = 'R' AND doi like ?", "id {}"),
        "all_equal_doi": ("WHERE", "type = 'R' AND doi = ?", "id {}"),

        # Get all Routed notifications for particular Repo Account
        # NB. ONLY Routed notifications will have entries in notification_account table
        "all_4rac_since_id": ("SQL", _select_all_4rac_part + "n.id > ? AND n.type = 'R'", "id {}"),
        "all_4rac_since_date": ("SQL", _select_all_4rac_part + "DATE(n.analysis_date) >= ?", "id {}"),
        "all_4rac_like_doi": ("SQL", _select_all_4rac_part + "n.doi like ? AND n.type = 'R'", "id {}"),
        "all_4rac_equal_doi": ("SQL", _select_all_4rac_part + "n.doi = ? AND n.type = 'R'", "id {}"),

        # Get all Routed notifications for particular Publisher Account
        "all_4pac_since_date": ("SQL", _select_all_4pub_ac_part + "DATE(n.analysis_date) >= ?", "id {}"),
        "all_4pac_like_doi": ("SQL", _select_all_4pub_ac_part + "n.doi like ? AND n.type = 'R'", "id {}"),
        "all_4pac_equal_doi": ("SQL", _select_all_4pub_ac_part + "n.doi = ? AND n.type = 'R'", "id {}"),

        ## Following for use with bespoke_pull() only ##

        # Retrieve ALL columns from both notification and match_provenance tables for notifications matching a particular account
        # IMPORTANT: The column order must match the order of entries in the __auto_sql_cols__, __auto_dao_cols__, __extra_cols__ lists
        # 2 params: Acc-ID, Minimum-analysis-date (aka from-date)
        "bspk_notes_with_prov": ("BSPK", _bspk_notes_matchprov_part + "DATE(n.analysis_date) >= ?", "n.id {}"),
        "bspk_notes_like_doi_with_prov": ("BSPK", _bspk_notes_matchprov_part + "n.doi LIKE ?", "n.id {}"),
        "bspk_notes_equal_doi_with_prov": ("BSPK", _bspk_notes_matchprov_part + "n.doi = ?", "n.id {}"),
        "bspk_one_note_with_prov": ("BSPK", _bspk_notes_matchprov_part + "na.id_note = ?", None),

        # Retrieve only the information required to retrieve Content (used for get content API call - saves having to retrieve & unpack MEDIUMTEXT json column)
        "bspk_4content": ("BSPK", "SELECT id, prov_id, repositories, pkg_format FROM notification WHERE id = ?", None),
        # Retrieve only the information required to retrieve Proxy content (used for get_proxy_url API call - saves having to retrieve & unpack MEDIUMTEXT json column)
        "bspk_links_4proxycontent": ("BSPK", "SELECT id, links_json FROM notification WHERE id = ?", None),

        # Publisher DOI Report query
        # Query takes 3 parameters: Pub-acc-id, First-date, Last-date  (will only select ROUTED notifications as only they have prov_id & analysis date set)
        "bspk_pub_doi_repo_data_in_range": ("BSPK",
                               "SELECT analysis_date, doi, repositories FROM notification WHERE prov_id = ? AND DATE(analysis_date) BETWEEN ? AND ?",
                               "1,2"),
        # "XXX all_r_ids_4ac_since_id": ("BSPK", "SELECT id FROM notification INNER JOIN notification_account AS na ON notification.id = na.id_note WHERE na.id_acc = ? AND id > ?", "id {}"),
        # "XXX all_r_ids_4ac_since_date": ("BSPK", "SELECT id FROM notification INNER JOIN notification_account AS na ON notification.id = na.id_note WHERE na.id_acc = ? AND analysis_date >= ?", "id {}"),
    }
    # These variables need initialising here because NotificationDAO (which this class inherits from) can be called
    # independently, which will set these values, which we don't want to inherit here.
    _all_cols = None
    _save_cols_names = None


class NotificationAccountDAO(TableDAOMixin):
    """
    DAO for NotificationAccount table - This associates Notifications with the repo Accounts they have been matched to.
    """
    __table__ = "notification_account"
    __ignore_null__ = True  # When retrieving recs, don't create data dict entries where record fields (cols) are NULL

    # List of tuples for columns that are created/updated by MySQL
    __auto_sql_cols__ = []
    # List of tuples for columns that are created/updated automatically by this DAO
    __auto_dao_cols__ = []

    __extra_cols__ = [("id_note", None, None),
                      ("id_acc", None, None)]
    __json__ = []   # No JSON stored
    __pks__ = ["id_note", "id_acc"]


class PubDepositRecordDAO(TableDAOMixin):
    """
    DAO for PubDepositRecords and all it's sub classes (API deposit records, FTP deposit records, etc..)
    """
    __table__ = "pub_deposit"
    __ignore_null__ = True  # When retrieving recs, don't create data dict entries where record fields (cols) are NULL

    # List of tuples for columns that are created/updated by MySQL
    __auto_sql_cols__ = [("id", None, None),
                         ("created", None, DAO.convert_datetime),
                         ("updated", None, DAO.convert_datetime)
                         ]
    # List of tuples for columns that are created/updated automatically by this DAO
    __auto_dao_cols__ = []

    __extra_cols__ = [("pub_id", None, None),
                      ("note_id", None, None),
                      ("type", None, None),
                      ("matched", None, None),
                      ("matched_live", None, None),
                      ("successful", None, None),
                      ("name", None, None),
                      ("error", None, None),
                      ("sword_in_progress", None, None),
                      ("err_emailed", None, None),
                      ]
    # No JSON structure to store
    __json__ = []
    __pks__ = ["id"]

    __pull_cursor_dict__ = {
        "pk": ("", __pks__, None),
        "note_id": ("", ["note_id"], None),     # For pulling by note_Id (expect max of 1 rec)
        "all_by_type": ("", ["type"], "id DESC"),   # This only used for testing, so no need to create index on `type`
        "all_4_pub": ("", ["pub_id"], "id DESC"),

        # The following queries are for use with bespoke_pull() function
        # bspk_daily_stats: calcs daily statistics and ONLY concatentates files & errors for unsuccessful deposits (successful is 0)
        "bspk_daily_stats":
            ("BSPK",
             "SELECT DATE(created) AS created, type, COUNT(id) AS total, CAST(SUM(successful) AS UNSIGNED) AS ok, CAST(SUM(matched) AS UNSIGNED) AS matched, CAST(IFNULL(SUM(matched_live), 0) AS UNSIGNED) AS matched_live, GROUP_CONCAT(IF(successful, NULL, name) SEPARATOR '|') AS files, GROUP_CONCAT(IF(successful, NULL, CONCAT(name, ' – ', error)) SEPARATOR '|') AS errors FROM pub_deposit WHERE pub_id = ? AND DATE(created) BETWEEN ? AND ? GROUP BY 1, 2",
             "1 DESC"),
        # This count query takes same parameters as its associated reporting query above.  It returns a single row, with
        # one integer value, which is the number of records that will be returned by above query
        "bspk_daily_stats_count":
            ("BSPK",
             "SELECT COUNT(DISTINCT DATE(created), type) as counter FROM pub_deposit WHERE pub_id = ? AND DATE(created) BETWEEN ? AND ?",
             None),

        "bspk_errmsg_by_id":
            ("BSPK", f"SELECT created, {_pub_error_part} FROM pub_deposit AS pd WHERE id = ?", None),

        # Takes 2 params: From-date, To-Date ("YYYY-MM-DD" format)
        # Returns: dup_count, pub_id, doi, file_names, deposit_dates, note_ids, metrics, repo_ids
        # Note that repo_ids may be duplicated - so will need de-duplication
        "bspk_duplicate_submissions":
            ("BSPK", "SELECT COUNT(pd.id) AS `dup_count`, GROUP_CONCAT(DISTINCT pd.pub_id SEPARATOR ',' ) AS pub_id, n.doi as doi, GROUP_CONCAT(DISTINCT pd.name ORDER BY 1 SEPARATOR ', ') AS `file_names`, GROUP_CONCAT(DATE(pd.created) ORDER BY 1 SEPARATOR ', ') AS `deposit_dates`, GROUP_CONCAT(pd.note_id ORDER BY 1 SEPARATOR ', ') AS `note_ids`, GROUP_CONCAT(distinct n.metrics_val ORDER BY 1 SEPARATOR ', ') AS `metrics`, GROUP_CONCAT(DISTINCT (SELECT GROUP_CONCAT(DISTINCT na.id_acc SEPARATOR ',' ) FROM notification_account na WHERE na.id_note = pd.note_id) SEPARATOR ',') AS repo_ids FROM pub_deposit pd JOIN notification n ON n.id = pd.note_id WHERE pd.matched_live = 1 AND DATE(pd.created) BETWEEN ? AND ? GROUP BY n.doi HAVING `dup_count` > 1", "1 DESC")
    }

    __delete_cursor_dict__ = {
        "pk": ("", ["id"], None),
        "older_than": ("WHERE", "created < ?", None)
    }

    __bespoke_update_insert_dict__ = {
        "update_err_emailed_true": "UPDATE pub_deposit SET err_emailed = 1 WHERE id = ?"
    }


class PubTestRecordDAO(TableDAOMixin):
    """
    DAO for PubTestRecords
    """
    __table__ = "pub_test"
    __ignore_null__ = True  # When retrieving recs, don't create data dict entries where record fields (cols) are NULL

    # List of tuples for columns that are created/updated by MySQL
    __auto_sql_cols__ = [("id", None, None),
                         ("created", None, DAO.convert_datetime)]
    # List of tuples for columns that are created/updated automatically by this DAO
    __auto_dao_cols__ = []

    __extra_cols__ = [("pub_id", None, None),
                      ("json_comp", None, None)
                      ]
    __pull_cursor_dict__ = {
        "pk": ("", ["id"], None),
        "all_4_pub": ("", ["pub_id"], "id DESC")
    }

    __delete_cursor_dict__ = {
        # "pk": ("", ["id"], None),     There is no need to delete individual records
        "older_than": ("WHERE", "created < ?", None)
    }


class SwordDepositRecordDAO(TableDAOMixin):
    """
    DAO for SWORD SwordDepositRecord
    """
    __table__ = "sword_deposit"
    __ignore_null__ = True  # When retrieving recs, don't create data dict entries where record fields (cols) are NULL

    # List of tuples for columns that are created/updated by MySQL
    __auto_sql_cols__ = [("id", None, None),
                         ("deposit_date", None, DAO.convert_datetime)]
    # List of tuples for columns that are created/updated automatically by this DAO
    __auto_dao_cols__ = []

    __extra_cols__ = [("note_id", None, None),
                      ("repo_id", None, None),
                      ("metadata_status", None, None),
                      ("content_status", None, None),
                      ("completed_status", None, None),
                      ("error_message", None, None),
                      ("doi", None, None),
                      ("edit_iri", None, None),
                      ("err_emailed", None, None),
                      ]
    # No JSON structure to store
    __json__ = []


    __pull_cursor_dict__ = {
        "pk": ("", ["id"], None),
        "all": ("", None, None),  # Select ALL records

        # Pull by repo_id and note_id, where metadata deposit was successful
        "by_note_id_repo_id_meta_ok": ("WHERE", "note_id = ? AND repo_id = ? AND metadata_status = 1", "id {}"),

        # Pull all where metadata_status is DEPOSITED, for specified repo_id and doi, sort by ID
        # ORDER BY clause direction (ASC or DESC) will be determined by the pull_all(order_by parameter)
        # 3 Params: repo_id, DOI
        "by_repo_id_and_doi": ("WHERE", "repo_id = ? AND doi = ? AND metadata_status = 1", "id {}"),

        # The following queries are for use with bespoke_pull() function
        # bspk_daily_for_repo: For a particular repository, aggregates deposit records into daily buckets, counting
        # the number of successes & failures. If errors, these are aggregated into a '|' separated string
        # Returns following columns: deposit_date, total, meta_ok, meta_failed, fulltext_ok, fulltext_failed, errors
        # Sorted in descending date order (most recent first)
        # 3 Params: repo-id, from-date, to-date
        "bspk_daily_for_repo":
            ("BSPK",
             "SELECT DATE(deposit_date) AS deposit_date, COUNT(*) as total, COUNT(IF(metadata_status = 1, 1, NULL)) AS meta_ok, COUNT(IF(metadata_status = 0, 1, NULL)) AS meta_failed, COUNT(IF(content_status = 1, 1, NULL)) AS fulltext_ok, COUNT(IF(content_status = 0, 1, NULL)) AS fulltext_failed, GROUP_CONCAT(IF(error_message IS NULL, NULL, CONCAT(IF(metadata_status = 0, 'Metadata', IF(content_status = 0, 'Content', 'Completion')), ' error: [ ', note_id, IF(content_status = 0 AND edit_iri IS NOT NULL, CONCAT(' • ', edit_iri), ''), ' • DOI: ', IFNULL(doi, 'unknown'), ' ]. ', error_message)) SEPARATOR '|') AS errors FROM sword_deposit WHERE repo_id = ? AND DATE(deposit_date) BETWEEN ? AND ? GROUP BY 1",
             "1 DESC"),
        # This count query takes same parameters as its associated reporting query above.  It returns a single row, with
        # one integer value, which is the number of records that will be returned by above query
        "bspk_daily_for_repo_count":
            ("BSPK",
             "SELECT COUNT(DISTINCT DATE(deposit_date)) AS counter FROM sword_deposit WHERE repo_id = ? AND DATE(deposit_date) BETWEEN ? AND ?",
             None),

        "bspk_errmsg_by_id":
            ("BSPK", f"SELECT deposit_date, {_sword_error_part} FROM sword_deposit AS sd WHERE id = ?", None)
    }

    __delete_cursor_dict__ = {
        "pk": ("", ["id"], None),
        "older_than": ("WHERE", "deposit_date < ?", None)
    }

    __bespoke_update_insert_dict__ = {
        "update_err_emailed_true": "UPDATE sword_deposit SET err_emailed = 1 WHERE id = ?"
    }


class HarvWebServiceRecordDAO(TableDAOMixin):
    """
    DAO for Harvester WebService record
    """
    __table__ = "h_webservice"
    __ignore_null__ = False  # When retrieving recs, DO create data dict entries (containing None) where record fields (cols) are NULL

    # List of tuples for columns that are created/updated by MySQL
    __auto_sql_cols__ = [("id", None, None),
                         ("updated", None, DAO.convert_datetime)
                         ]
    # List of tuples for columns that are created/updated automatically by this DAO
    __auto_dao_cols__ = []
    __extra_cols__ = [("name", None, None),
                      ("url", None, None),
                      ("query", None, None),
                      ("frequency", None, None),
                      ("active", None, None),
                      ("email", None, None),
                      ("engine", None, None),
                      ("wait_window", None, None),
                      ("publisher", None, None),
                      ("end_date", None, None),     # End_date is CHAR (not DATETIME)
                      ("live_date", None, DAO.empty_str_to_null),     # Live_date is CHAR (not DATETIME)
                      ("notes", None, None),
                      ("auto_enable", None, None),
                      ]
    # No JSON structure to store
    __json__ = []
    __pks__ = ["id"]

    __pull_cursor_dict__ = {
        "pk": ("", __pks__, None),
        "all": ("", None, None),      # Select ALL records
        "active": ("WHERE", "active = 1", None ),
        "pub_or_not": ("WHERE", "publisher = ?", "name ASC"),  # ALL records which are either publisher OR true harvester
        # The following queries are for use with bespoke_pull() function
        "bspk_test_harv_ids": ("BSPK", "SELECT id FROM h_webservice WHERE live_date IS NULL", None),
        # Return ID of harvester-webservice recs where auto_enable is 1 or 0 (depending on supplied parameter)
        "bspk_auto_enable_harv_ids": ("BSPK", "SELECT id FROM h_webservice WHERE IFNULL(auto_enable, 0) = ?", "id ASC")
    }


class HarvErrorRecordDAO(TableDAOMixin):
    """
    DAO for Harvester Error record
    """
    __table__ = "h_errors"
    __ignore_null__ = True  # When retrieving recs, don't create data dict entries where record fields (cols) are NULL

    # List of tuples for columns that are created/updated by MySQL
    __auto_sql_cols__ = [("id", None, None),
                         ("created", None, DAO.convert_datetime)
                         ]
    # List of tuples for columns that are created/updated automatically by this DAO
    __auto_dao_cols__ = []
    __extra_cols__ = [("ws_id", None, None),
                      ("hist_id", None, None),
                      ("error", None, None),
                      ("document", None, None),
                      ("url", None, None),
                      ]
    # No JSON structure to store
    __json__ = []
    __pks__ = ["id"]

    _all_select_with_join = "SELECT e.id, e.created, w.name, e.error, e.url, e.document, e.ws_id, e.hist_id FROM h_errors AS e INNER JOIN h_webservice as w ON e.ws_id = w.id"
    
    __pull_cursor_dict__ = {
        "pk": ("", __pks__, None),
        "all": ("", None, None),
        "all_4hist": ("", ["hist_id"], None),   # For counting all records that would be returned by "bspk_all_4hist"
        # The following queries are for use with bespoke_pull() function
        # The ORDER BY "id DESC" ensures most recent listed first
        "bspk_all": ("BSPK", _all_select_with_join, "id DESC"),
        "bspk_all_4hist": ("BSPK", _all_select_with_join + " WHERE e.hist_id = ?", "id DESC")
    }
    __delete_cursor_dict__ = {
        # "for_ws_id": ("WHERE", "ws_id = ?", None),
        "for_ws_id": ("", ["ws_id"], None),
        "older_than": ("WHERE", "created < ?", None)
    }


class HarvHistoryRecordDAO(TableDAOMixin):
    """
    DAO for Harvester History record
    """
    __table__ = "h_history"
    __ignore_null__ = True  # When retrieving recs, don't create data dict entries where record fields (cols) are NULL
    # List of tuples for columns that are created/updated by MySQL
    __auto_sql_cols__ = [("id", None, None),
                         ("created", None, DAO.convert_datetime)
                         ]
    # List of tuples for columns that are created/updated automatically by this DAO
    __auto_dao_cols__ = []
    __extra_cols__ = [("ws_id", None, None),
                      ("query", None, None),
                      ("url", None, None),
                      ("start_date", None, None),   # Start_date is CHAR(10) (not DATETIME)
                      ("end_date", None, None),     # End_date is CHAR(10) (not DATETIME)
                      ("num_received", None, None),
                      ("num_sent", None, None),
                      ("num_errors", None, None),
                      ]
    # No JSON structure to store
    __json__ = []
    __pks__ = ["id"]

    _select_with_join = "SELECT h.id, h.created, w.name, h.url, h.start_date, h.end_date, h.num_received, h.num_sent, h.num_errors, h.ws_id FROM h_history AS h INNER JOIN h_webservice as w ON h.ws_id = w.id"
    
    __pull_cursor_dict__ = {
        "pk": ("BSPK", _select_with_join + " WHERE h.id = ?", None),
        "all": ("", None, None),                  # Select ALL records from h_history, ORDER BY id DESC
        # Following queries are for use with bespoke_pull() function
        # Select ALL records from h_history JOINED to h_webservice, ORDER BY id DESC (most recent first)
        "bspk_all": ("BSPK", _select_with_join, "id DESC"),
    }
    __delete_cursor_dict__ = {
        # "for_ws_id": ("WHERE", "ws_id = ?", None),
        "for_ws_id": ("", ["ws_id"], None),
        "older_than": ("WHERE", "created < ?", None)
    }


class MetricsRecordDAO(TableDAOMixin):
    """
    DAO for Metrics.
    """
    __table__ = "metrics"
    __ignore_null__ = True  # When retrieving recs, don't create data dict entries where record fields (cols) are NULL

    # List of tuples for columns that are created/updated by MySQL
    __auto_sql_cols__ = [("id", None, None)]
    # List of tuples for columns that are created/updated automatically by this DAO
    __auto_dao_cols__ = []

    __extra_cols__ = [("start", None, DAO.convert_datetime),
                      ("duration", None, DAO.convert_decimal),
                      ("server", None, None),
                      ("proc_name", None, None),
                      ("measure", None, None),
                      ("count", None, None),
                      ]
    __pks__ = ["id"]

    _bspk_part = "SELECT start, server, proc_name, measure, count, duration as secs, ROUND(duration / 60, 1) as mins, json FROM metrics m "
    
    __pull_cursor_dict__ = {
        "pk": ("", __pks__, None),
        "all_with_count": ("WHERE", "count >= ?", None),
        "bspk_all_with_count":  ("BSPK", _bspk_part + "WHERE count >= ?", "start DESC"),
        # The following take 2 params [Minimum-count, Process-name]
        "all_with_count_of_type": ("WHERE", "count >= ? AND proc_name = ?", None),
        "bspk_all_with_count_of_type": ("BSPK", _bspk_part + "WHERE count >= ? AND proc_name = ?", "start DESC"),
        # Following query requires 3 parameters [minimum-count (normally 0 or 1), from-date, to-date]
        "range_with_count": ("WHERE", "count >= ? AND DATE(start) BETWEEN ? AND ?", None),
        "bspk_range_with_count": ("BSPK", _bspk_part + "WHERE count >= ? AND DATE(start) BETWEEN ? AND ?", "start DESC"),
        # The following take 4 params [minimum-count, from-date, to-date, Process-name]
        "range_with_count_of_type": ("WHERE", "count >= ? AND DATE(start) BETWEEN ? AND ? AND proc_name = ?", None),
        "bspk_range_with_count_of_type": ("BSPK", _bspk_part + "WHERE count >= ? AND DATE(start) BETWEEN ? AND ? AND proc_name = ?", "start DESC"),
        # No params - special case
        "bspk_list_proc_names": ("BSPK", "SELECT DISTINCT proc_name from metrics ", None),
        # count is included in the following queries so that the Indexes are used
        "bspk_max_durations": ("BSPK", _bspk_part + "WHERE m.count > 0 AND m.duration = (SELECT MAX(mm.duration) FROM metrics mm WHERE mm.count > 0 AND mm.proc_name = m.proc_name)", "duration DESC"),
        "bspk_max_durations_range": ("BSPK", _bspk_part + "WHERE m.count > 0 AND DATE(m.start) BETWEEN ? AND ? AND m.duration = (SELECT MAX(mm.duration) FROM metrics mm WHERE mm.count > 0 AND mm.proc_name = m.proc_name AND DATE(mm.start) BETWEEN ? AND ?)", "duration DESC"),
    }

    __delete_cursor_dict__ = {
        # "pk": ("", ["id"], None),
        # "older_than": ("WHERE", "start < ?", None),
        "older_than_count": ("WHERE", "start < ? AND count = 0", None)
    }


class MonthlyInstitutionStatsDAO(TableDAOMixin):
    """
    DAO for Monthly institution statistics - which records monthly stats for each institution (repository/CRIS)
    """
    __table__ = "monthly_institution_stats"
    # List of tuples for columns that are created/updated by MySQL
    __auto_sql_cols__ = []
    __auto_dao_cols__ = []
    __extra_cols__ = [("year_month_date", None, DAO.convert_date),
                      ("type", None, None),
                      ("acc_id", None, None),
                      ("metadata_only", None, None),
                      ("with_content", None, None),
                      ]
    __json__ = []
    __pks__ = ["year_month_date", "type", "acc_id"]

    __pull_cursor_dict__ = {
        "pk": ("AND", __pks__, None),
        # Return monthly data for Live or Test accounts between 2 dates (normally YYYY-01-01 and YYYY-12-01)
        # Sorted by org_name and year_month_date
        # LEFT JOIN is used so returns unique rows, for which a.org_name is NULL
        # Note that the data for unique counts has an org-name of "zUnique" so it appears last
        # Query takes 3 parameters: Type 'L' (Live) or 'T' (Test), First-date, Last-date
        "bspk_repo_annual_data": ("BSPK", "SELECT COALESCE(a.org_name, 'zUnique') AS org_name, mis.year_month_date, a.r_repo_name, mis.metadata_only, mis.with_content, mis.acc_id, LEFT(a.live_date, 10) AS live_date, a.r_identifiers FROM monthly_institution_stats AS mis LEFT JOIN account AS a ON mis.acc_id = a.id WHERE mis.type = ? AND mis.year_month_date BETWEEN ? AND ?", "1, 2")
    }

    __bespoke_update_insert_dict__ = {
        # Bespoke bulk insert statements for creating institution monthly stats records
        # Each takes 3 parameters, in this order: [First-of-month-date, First-of-month-date, Last-day-of-month-date]
        "insert_live_monthly_by_ac": "INSERT INTO monthly_institution_stats (year_month_date, type, acc_id, metadata_only, with_content) SELECT ?, 'L', na.id_acc, SUM(ISNULL(n.links_json)) AS metadata_only, COUNT(n.links_json) AS num_with_content FROM notification AS n INNER JOIN notification_account AS na ON n.id = na.id_note INNER JOIN account AS a ON a.id = na.id_acc WHERE DATE(n.analysis_date) BETWEEN ? AND ? AND n.analysis_date >= a.live_date GROUP BY 3",
        "insert_test_monthly_by_ac": "INSERT INTO monthly_institution_stats (year_month_date, type, acc_id, metadata_only, with_content) SELECT ?, 'T', na.id_acc, SUM(ISNULL(n.links_json)) AS metadata_only, COUNT(n.links_json) AS num_with_content FROM notification AS n INNER JOIN notification_account AS na ON n.id = na.id_note INNER JOIN account AS a ON a.id = na.id_acc WHERE DATE(n.analysis_date) BETWEEN ? AND ? AND (a.live_date IS NULL OR n.analysis_date < a.live_date) GROUP BY 3",
        "insert_live_monthly_unique": "INSERT INTO monthly_institution_stats (year_month_date, type, acc_id, metadata_only, with_content) SELECT ?, 'L', 0, COUNT(DISTINCT IF(ISNULL(n.links_json), n.id, NULL)) AS unique_meta_only, COUNT(DISTINCT IF(ISNULL(n.links_json), NULL, n.id)) AS unique_content FROM notification AS n INNER JOIN notification_account AS na ON n.id = na.id_note INNER JOIN account AS a ON a.id = na.id_acc WHERE DATE(n.analysis_date) BETWEEN ? AND ? AND n.analysis_date >= a.live_date",
        "insert_test_monthly_unique": "INSERT INTO monthly_institution_stats (year_month_date, type, acc_id, metadata_only, with_content) SELECT ?, 'T', 0, COUNT(DISTINCT IF(ISNULL(n.links_json), n.id, NULL)) AS unique_meta_only, COUNT(DISTINCT IF(ISNULL(n.links_json), NULL, n.id)) AS unique_content FROM notification AS n INNER JOIN notification_account AS na ON n.id = na.id_note INNER JOIN account AS a ON a.id = na.id_acc WHERE DATE(n.analysis_date) BETWEEN ? AND ? AND (a.live_date IS NULL OR n.analysis_date < a.live_date)"
    }

    __delete_cursor_dict__ = {
        "for_month": ("", ["year_month_date"], None),
    }


class MonthlyPublisherStatsDAO(TableDAOMixin):
    """
    DAO for Monthly publisher statistics - which records monthly stats for each publisher.
    """
    __table__ = "monthly_publisher_stats"
    # List of tuples for columns that are created/updated by MySQL
    __auto_sql_cols__ = []
    __auto_dao_cols__ = []
    __extra_cols__ = [("year_month_date", None, DAO.convert_date),
                      ("acc_id", None, None),
                      ("received", None, None),
                      ("matched", None, None),
                      ]
    __json__ = []
    __pks__ = ["year_month_date", "acc_id"]

    __pull_cursor_dict__ = {
        "pk": ("AND", __pks__, None),
        # Return monthly data for Publisher accounts between 2 dates (normally YYYY-01-01 and YYYY-12-01)
        # Sorted by org_name and year_month_date
        # Query takes 2 parameters: First-date, Last-date
        "bspk_pub_annual_data": ("BSPK", "SELECT a.org_name, mps.year_month_date, mps.received, COALESCE(mps.matched, 0), mps.acc_id FROM monthly_publisher_stats AS mps INNER JOIN account AS a ON mps.acc_id = a.id WHERE mps.year_month_date BETWEEN ? AND ?", "1, 2")
    }

    __bespoke_update_insert_dict__ = {
        # Bespoke bulk insert statement for creating publisher monthly stats records
        # Takes 3 parameters, in this order: [First-of-month-date, First-of-month-date, last-day-of-month date]
        "insert_pub_monthly_stats": "INSERT INTO monthly_publisher_stats (year_month_date, acc_id, received, matched) SELECT ?, pub_id, SUM(successful) AS received, SUM(matched_live) AS matched FROM pub_deposit WHERE DATE(created) BETWEEN ? AND ? GROUP BY 2"
    }

    __delete_cursor_dict__ = {
        "for_month": ("", ["year_month_date"], None),
    }


class MonthlyHarvesterStatsDAO(TableDAOMixin):
    """
    DAO for Monthly harvester statistics - which records monthly stats for each harvester.
    """
    __table__ = "monthly_harvester_stats"
    # List of tuples for columns that are created/updated by MySQL
    __auto_sql_cols__ = []
    __auto_dao_cols__ = []
    __extra_cols__ = [("year_month_date", None, DAO.convert_date),
                      ("acc_id", None, None),
                      ("received", None, None),
                      ("matched", None, None),
                      ]
    __json__ = []
    __pks__ = ["year_month_date", "ws_id"]

    __pull_cursor_dict__ = {
        "pk": ("AND", __pks__, None),
        # Return monthly data for Harvester webservice accounts between 2 dates (normally YYYY-01-01 and YYYY-12-01)
        # Sorted by name and year_month_date
        # Query takes 2 parameters: First-date, Last-date
        "bspk_harv_annual_data": ("BSPK", "SELECT hw.name, mhs.year_month_date, mhs.received, COALESCE(mhs.matched, 0), mhs.acc_id FROM monthly_harvester_stats AS mhs INNER JOIN h_webservice AS hw ON mhs.acc_id = hw.id WHERE mhs.year_month_date BETWEEN ? AND ?", "1, 2"),
    }

    __bespoke_update_insert_dict__ = {
        # Bespoke bulk insert statement for creating harvester monthly stats records
        # Inserting for each web-service the Total recs harvested & Total recs matched to a LIVE repository
        # Takes 5 parameters, in this order: [First-of-month-date, First-of-month-date, last-day-of-month date, First-of-month-date, last-day-of-month date]
        "insert_harv_monthly_stats": "INSERT INTO monthly_harvester_stats (year_month_date, acc_id, received, matched) SELECT ?, hh.ws_id, SUM(hh.num_sent) AS received, (SELECT COUNT(DISTINCT n.id) FROM notification AS n INNER JOIN notification_account AS na ON n.id = na.id_note INNER JOIN account AS a on a.id = na.id_acc WHERE hh.ws_id = n.prov_harv_id AND DATE(n.analysis_date) BETWEEN ? AND ? AND n.type = 'R' AND n.analysis_date >= a.live_date) AS matched FROM h_history AS hh WHERE DATE(hh.created) BETWEEN ? AND ? GROUP BY 2"
    }

    __delete_cursor_dict__ = {
        "for_month": ("", ["year_month_date"], None),
    }

