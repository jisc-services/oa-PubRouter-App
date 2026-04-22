"""
Models associated with BOTH Organisation (AccOrg) and User (AccUser) Accounts.
(Account records are stored in separate DB tables: AccOrg -> `account`; AccUser -> `acc_user`).

Note that AccUser object may contain its parent AccOrg object (the exception is when an AccUser is retrieved on its
own, without its associated organisation record).

There are 3 types of AccOrg: Admin account - for Jisc administrators, Publisher account, Repository account.
"""

import uuid
from csv import reader as csv_reader
import re
from copy import deepcopy
from datetime import datetime
from dateutil.relativedelta import relativedelta
from random import randint
from logging import INFO, WARNING
from flask import current_app, url_for
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from octopus.modules.logger.logger import ERROR_X
from octopus.lib.data import list_get
from octopus.lib.files import bytes_io_to_string_io
from octopus.lib import dataobj, dates
from octopus.lib.mail import MailMsg, MailAccount, environment_name
from octopus.lib.shellscript import run_script_return_err_code
from router.shared.mysql_dao import AccOrgDAO, AccUserDAO, AccNotesEmailsDAO, AccRepoMatchParamsDAO, \
    AccRepoMatchParamsArchivedDAO, AccBulkEmailDAO, RAW, DICT, WRAP, CONN_CLOSE
from router.shared.models.child import DAOChild
from router.shared.shellscript import full_script_path


# Status options
OFF = 0
OKAY = 1
FAILING = 2     # Repos: More serious than PROBLEM - Despite repeated attempts, the deposit has failed
PROBLEM = 3     # Repos: Indicates that a deposit problem exists, but repeated attempts will be made to achieve success

# Regex to match a colon with optional following space
split_org_id_regex = re.compile(r': ?')
match_multispace_regex = re.compile(r'\s+')   # Match one or more white space characters
includes_regex = re.compile(r'[\\|+?[]')      # test if a match-param name variant includes REGEX

# scroll_num values: help ensure that Scrollers use unique connections (though uniqueness is conferred by scroll_name
# which is a composite of scroll_num, pull_name and other attributes).
# IMPORTANT check entire code base for other similar declarations before adding new ones (or changing these numbers) to
# avoid overlaps - do global search for "_SCROLL_NUM ="
AC_ERRORS_SCROLL_NUM = 25
REPO_MATCH_PARAM_SCROLL_NUM = 26
REPO_AC_SCROLL_NUM = 27


def list_to_delimited_string(list_):
    return "; ".join(list_)


class RepositoryData(DAOChild):
    """
    Specific repository model details for repository account users.
    Inherits from DAOChild, so that Organisation Account can pass on it's id and save() methods in the init.

        "repository_data": { // these fields will only be populated if the user is of type repository
            "excluded_provider_ids" : "<Ids of notification providers to be excluded from matching><list of strings>",
            "identifiers": [{'type': 'identifier type (JiscID, COREID, etc..', 'id': 'actual id value'}]<list objects>,
            "max_pub_age": "<maximum age of publication a repo is interested in receiving><int>",
            "repository_info": {
                "name": "<name of the repository><string>",
                "url": "<url for the repository><string>",
                "software": "<name of the software><string>",
                "xml_format": "<format of XML to send to repository could be Eprint or RIOXX><string>",
                "target_queue": "<Eprints only: Target queue in which notifications should be deposited><string>",
                "packaging": "<packaging URI to be used in deposits to this respository><string>"
            },
            "sword": {
                "username" : "<username for the router to authenticate with the repository>",
                "password" : "<reversibly encrypted password for the router to authenticate with the repository>",
                "collection" : "<url for deposit collection to receive content from the router>",
                "last_updated" : "<timestamp "%Y-%m-%dT%H:%M:%SZ" when this record was last updated>",
                "last_deposit_date" : "<timestamp "%Y-%m-%dT%H:%M:%SZ" of analysed date of last deposited notification>",
                "last_note_id": "<Id of last notification deposited>",
                "retries" : "<number of attempted deposits>",
                "last_tried" : "<timestamp of last attempted failed deposit or None if deposit is successful>"
            },
            "duplicates": {
                "level_h": "<Int - Indicates level of HARVESTER duplicates which should be routed:
                            0: No duplicates
                            1: Essential duplicates only
                            2: Duplicates with changes in numbers of things (see doi_register.py for further info)
                            3: Duplicates with new High value fields
                            4: Duplicates with new Med value fields
                            5: Duplicates with new Low value fields
                            6: All duplicates (even those with no obvious differences) >"
               "level_p": "<Int - Indicates level of PUBLISHER duplicates which should be routed:
                            See above values"
                "emails": ["<list of email addresses to send duplicate notifications to>"],
                "meta_format": <"String - 'txt', 'xml' or 'json' - determines how Metadata is sent in Email">
            }
        }
    }
    """

    def _get_identifier_by_type(self, type, return_index=False):
        """
        Helper function to return either an identifier's value or it's index in the list of identifiers

        :param type: Type of identifier
        :param return_index: Boolean - False: return the identifier's value | True: return index in list of identifiers

        :return: Index of identifier in list or value of identifier if found, otherwise None.
        """

        identifiers = self.identifiers

        found_item = None
        # Loop thru identifiers associated with account
        for index, identifier in enumerate(identifiers):
            # Have found required type
            if identifier.get("type") == type:
                if return_index:
                    found_item = index
                else:
                    found_item = identifier.get("id")
                break
        return found_item

    def _set_identifier(self, type, value):
        """
        Add or replace an identifier of a certain type with a new value. For example, if there is already a
        JISC type identifier, and you wish to add a new one, this will replace it. Elsewise, it will append the
        identifier to the list of identifiers.

        :param type: Type of identifier to add/replace
        :param value: ID value to give the identifier
        """
        ids = self.identifiers
        # Get index to identifier (in list), will be None if not already stored
        type_index = self._get_identifier_by_type(type, return_index=True)
        id_dict = {"type": type, "id": value}

        # If it already exists in the list, replace it - otherwise simply append.
        if type_index is not None:
            ids[type_index] = id_dict
        else:
            ids.append(id_dict)

    @property
    def jisc_id(self):
        return self._get_identifier_by_type("JISC")

    @jisc_id.setter
    def jisc_id(self, val):
        self._set_identifier("JISC", val)

    @property
    def core_id(self):
        return self._get_identifier_by_type("CORE")

    @core_id.setter
    def core_id(self, val):
        self._set_identifier("CORE", val)

    @property
    def dups_level_pub(self):
        return self._get_single("duplicates.level_p", default=0)

    @dups_level_pub.setter
    def dups_level_pub(self, val):
        self._set_single("duplicates.level_p", val)

    @property
    def dups_level_harv(self):
        return self._get_single("duplicates.level_h", default=0)

    @dups_level_harv.setter
    def dups_level_harv(self, val):
        self._set_single("duplicates.level_h", val)

    def dups_wanted(self, is_publisher, note_dup_level):
        """
        Decide if duplicate at the level specified by parameter is wanted by this repository
        :param is_publisher: Boolean - True: notification is from Publisher; False: notification is harvested
        :param note_dup_level: Integer - Notification duplicate level:
                0: Not a duplicate, 1: Duplicate is essential ... 6: Duplicate has no discernible difference
        :return: Boolean - True: The current duplicate notification is wanted; False: current duplicate not wanted by account
        """
        # return note_dup_level <= self.dups_level_pub if is_publisher else note_dup_level <= self.dups_level_harv
        return note_dup_level <= (self.dups_level_pub if is_publisher else self.dups_level_harv)

    @property
    def dups_emails(self):
        return self._get_list("duplicates.emails")

    @dups_emails.setter
    def dups_emails(self, val):
        self._set_list("duplicates.emails", val,  coerce=dataobj.to_uc_lower)

    def dups_emails_as_str(self):
        return ", ".join(self.dups_emails)

    @property
    def dups_meta_format(self):
        return self._get_single("duplicates.meta_format")

    @dups_meta_format.setter
    def dups_meta_format(self, val):
        self._set_single("duplicates.meta_format", val)

    @property
    def identifiers(self):
        # "identifiers": [{'type': 'identifier type (JiscID, COREID, etc..', 'id': 'actual id value'}]<list objects>
        return self._get_list("identifiers")

    @identifiers.setter
    def identifiers(self, val):
        self._set_list("identifiers", val)

    @property
    def packaging(self):
        return self._get_single("repository_info.packaging")

    @packaging.setter
    def packaging(self, val):
        self._set_single("repository_info.packaging", val)

    @property
    def sword_data(self):
        return self._get_single("sword")

    @sword_data.setter
    def sword_data(self, dict_value):
        self._set_single("sword", dict_value)

    def add_sword_credentials(self, username, password, collection):
        """
        Add the sword credentials for the user
        :param username: username to deposit to repository as
        :param password: password of repository user account
        :param collection: collection url to deposit to (or None if empty)
        """
        self._set_single("sword.username", username)
        self._set_single("sword.password", password)
        self._set_single("sword.collection", collection or None)

    @property
    def sword_collection(self):
        return self._get_single("sword.collection")

    @property
    def sword_username(self):
        return self._get_single("sword.username")

    @property
    def sword_password(self):
        return self._get_single("sword.password")

    @property
    def repository_software(self):
        return self._get_single("repository_info.software")

    @repository_software.setter
    def repository_software(self, val):
        self._set_single("repository_info.software", val)

    @property
    def repository_url(self):
        return self._get_single("repository_info.url")

    @repository_url.setter
    def repository_url(self, val):
        self._set_single("repository_info.url", val)

    @property
    def repository_xml_format(self):
        return self._get_single("repository_info.xml_format")

    @repository_xml_format.setter
    def repository_xml_format(self, val):
        self._set_single("repository_info.xml_format", val)

    @property
    def repository_queue(self):
        return self._get_single("repository_info.target_queue")

    @repository_queue.setter
    def repository_queue(self, val):
        self._set_single("repository_info.target_queue", val)

    @property
    def repository_name(self):
        return self._get_single("repository_info.name", default="")

    @repository_name.setter
    def repository_name(self, val):
        self._set_single("repository_info.name", val)

    def in_progress_eprints(self):
        """
        In eprints, the in_progress sword header will send the deposit to 'Manage Deposits' if set to True.
        If it's set to false, it sends the deposit to the 'Review Queue'.
        :return: If the target_queue is NOT set to review, return True. else, return False.
        """

        return self.repository_queue != "review"

    def is_eprints(self):
        # returns True if repository_xml_format is some type of eprints, otherwise False.
        return "eprints" in self.repository_xml_format

    def is_dspace(self):
        # returns True if repository_xml_format is some type of dspace, otherwise False.
        return "dspace" in self.repository_xml_format

    # REPOSITORY CONFIG RELATED STUFF

    @property
    def max_pub_age(self):
        return self._get_single("max_pub_age")

    @max_pub_age.setter
    def max_pub_age(self, val):
        self._set_single("max_pub_age", val, coerce=int)

    @property
    def excluded_provider_ids(self):
        return self._get_list("excluded_provider_ids")

    @excluded_provider_ids.setter
    def excluded_provider_ids(self, val):
        self._set_list("excluded_provider_ids", val)

    @property
    def last_deposit_date(self):
        # a date string of format YYYY-MM-DDTHH:MM:SSZ
        return self._get_single("sword.last_deposit_date")

    @last_deposit_date.setter
    def last_deposit_date(self, val):
        # a date string of format YYYY-MM-DDTHH:MM:SSZ
        self._set_single("sword.last_deposit_date", val, coerce=dataobj.date_str())

    @property
    def last_deposited_note_id(self):
        # ID (int) Of last notification deposited
        return self._get_single("sword.last_note_id")

    @last_deposited_note_id.setter
    def last_deposited_note_id(self, val):
        # ID (int) Of last notification deposited
        self._set_single("sword.last_note_id", val)

    @property
    def status(self):
        return self.parent.status    # NB. status "lives" in the parent structure

    @status.setter
    def status(self, val):
        # NB. status "lives" in the parent structure
        if val is not None and val not in (OFF, OKAY, FAILING, PROBLEM):
            raise dataobj.DataSchemaException(f"Value {val} is not permitted for repository status")
        self.parent.status = val

    def toggle_status_on_off(self):
        # toggles the repository's status between "off" and "okay"
        # returns the new status
        return self._set_repository_status(OFF if self.status != OFF else OKAY)

    @property
    def retries(self):
        return self._get_single("sword.retries", default=0)

    @retries.setter
    def retries(self, val):
        self._set_single("sword.retries", val, coerce=dataobj.to_int)

    @property
    def last_tried(self):
        # a date string of format YYYY-MM-DDTHH:MM:SSZ
        return self._get_single("sword.last_tried")

    @last_tried.deleter
    def last_tried(self):
        self._delete("sword.last_tried")

    @property
    def last_tried_timestamp(self):
        # last tried date as a timestamp
        return self._get_single("sword.last_tried", coerce=dataobj.to_datetime_obj())

    @last_tried.setter
    def last_tried(self, val):
        # a date string of format YYYY-MM-DDTHH:MM:SSZ
        self._set_single("sword.last_tried", val, coerce=dataobj.date_str())

    def record_failure(self, limit):
        """
        Record a failed attempt to deposit to this repository.

        The limit specifies the number of retries before the repository moves from the status "problem" to "failing"

        This will set the last_tried date, and increment the number of retries by 1, and set the status to "problem".

        If the new retry number is greater than the supplied limit,
        the number of last_tried date will be removed, retries will be set to 0, and the status set to "failing"

        :param limit: maximum number of retries before repository is considered to be completely failing
        :return: Boolean - True if failing, False if problem  (Note that "failing" is more serious)
        """
        self.retries = self.retries + 1
        failing = self.retries > limit
        if failing:
            self.last_tried = None
            self.retries = 0
            self.status = FAILING
        else:
            self.last_tried = dates.now_str()
            self.status = PROBLEM

        return failing

    def can_retry(self, delay):
        """
        For a "problem" repository, is it time to re-try again yet, given the delay.

        This will compare the last_tried date to the current time, and determine if the delay has elapsed

        :param delay: retry delay in seconds
        :return: True if suitable to re-try again, False if not
        """
        ts = self.last_tried_timestamp
        if ts is None:
            return True
        limit = dates.before_now(delay)
        return ts < limit

    def _set_repository_status(self, status):
        """
        Set the repository status.

        If the status is "okay", also reset the last_tried field.

        :param status: String of either okay, failing or off. if it is none of these, do nothing.
        :return: New status
        """
        self.status = status
        self.retries = 0
        if status == OKAY:
            self.last_tried = None
        return status

    def toggle_repo_status(self):
        # toggles the repository's status between "okay" or "problem" and "failing"
        # returns the new status
        return self._set_repository_status(OKAY if self.status == FAILING else FAILING)

    def repository_activate(self):
        # Set the current status to "okay".
        self._set_repository_status(OKAY)

    def repository_off(self):
        # Set the current status to "off".
        self._set_repository_status(OFF)

    def repository_deactivate(self):
        # Set the current status to "failing".
        self._set_repository_status(FAILING)

    # def get_matching_config_dict(self):
    #     matching_params_dict = AccRepoMatchParams.pull(self.id, wrap=False)
    #     return matching_params_dict.get("matching_config", {}) if matching_params_dict else {}


class PublisherData(DAOChild):
    """
    Specific publisher model details for publisher account users.
    Inherits from DAOChild, so that Organisation Account can pass on it's id and save() methods in the init.

        "publisher_data": { // these fields will only be populated if the user is of type publisher
            "embargo": [<list of objects> of format {
                'type': 'type of embargo: post_pub or pre_bug',
                'duration': 'value of duration (months)' }
                ]<list of objects>,
            "license": [<list of objects> of format {
                "title": "<default license title><string>",
                "type": "<default license type><string>",
                "url": "<default license url><string>",
                "version": "<default license version><string>" }
                ]<list of objects>,
            "peer_reviewed": "<Boolean 'true'/'false' - whether ALL articles are peer-reviewed><boolean>",
            "in_test": "<Boolean 'true'/'false' - whether testing in progress><boolean>",
            "testing": {
                "type": "<type of agreement: 'u'= AM or VoR upon Publication; 'b' = AM before publication><string>",
                "start": "<start date - YYYY-MM-DD><date>",
                "end": "<ended date - YYYY-MM-DD><date>",
                "emails": ["<list of email addresses to send test reports to>"],
                "last": "<last submission date - YYYY-MM-DD><date>",
                "last_err": "<date of last error - YYYY-MM-DD><date>",
                "last_ok": "<date of last successful submission - YYYY-MM-DD><date>",
                "num_err": "<Num errored submissions in test mode><integer>",
                "num_ok": "<Num ok submissions in test mode><integer>",
                "num_ok_since_err": "<num OK submissions since last error>",
                "route_note": "<Boolean 'true'/'false' - whether to create & route a notification>"
                }
            "reports":{
                "format": "<Report format indicator CHAR(1) -
                                "": Don't produce report
                                "C": Concatenate repo names, separate each by semicolon;
                                "N": Concatenate repo names, separate each by semicolon & newline "\n")
                                "S": Separate lines for each repo;
                                "B": Separate lines for each repo, but blank (don't repeat) other values><string>",
                "emails": ["<list of email addresses to send reports to>"],
                }
        }
    """

    @property
    def embargo(self):
        # currently only gets the duration value of the first embargo
        # note when implementation of multiple embargo types occurs, this will have to change
        embargoes = self._get_list("embargo")
        return list_get(embargoes, 0, default={}).get("duration", None)

    @embargo.setter
    def embargo(self, val):
        # note when implementation of multiple embargo types occurs, this will have to change
        self._set_list("embargo", [{"duration": val, "type": ""}])

    @property
    def license(self):
        """
        Retrieve FIRST licence from list of licenses
        {
            "title" : {"coerce" : "unicode"},
            "type" : {"coerce" : "unicode"},
            "url" : {"coerce" : "unicode"},
            "version" : {"coerce" : "unicode"}
        }
        """
        return list_get(self._get_list("license"), 0, default={})

    @license.setter
    def license(self, obj):
        """
        Set single element licence list (or empty list)
        """
        lic_list = [] if obj is None else [obj]
        self._set_single("license", lic_list)

    def set_license(self, title="", type="", url="", version=""):
        """
        Set the license info.

        :param url: the url where more information about the licence can be found
        :param type: the name/type of the licence (e.g. CC-BY)
        :param title: title of the licence
        :param version: version of the licence
        """
        license = {
            "title": title,
            "type": type,
            "url": url,
            "version": version
        }
        self.license = license

    @property
    def peer_reviewed(self):
        return self._get_single("peer_reviewed", coerce=dataobj.to_bool, default=False)

    @peer_reviewed.setter
    def peer_reviewed(self, val):
        self._set_single("peer_reviewed", val, coerce=dataobj.to_bool)


    @property
    def status(self):
        return self.parent.status    # NB. status "lives" in the parent structure

    @status.setter
    def status(self, val):
        if val is not None and val not in (OKAY, OFF):
            raise dataobj.DataSchemaException(f"Value {val} is not permitted for publisher status")
        self.parent.status = val

    def is_deactivated(self):
        status = self.status
        return not status or status == OFF

    def toggle_status_on_off(self):
        # toggles the publisher's status between "off" and "okay"
        # returns the new status
        new_status = OKAY if self.is_deactivated() else OFF
        self.status = new_status
        return new_status

    @property
    def report_format(self):
        return self._get_single("reports.format")

    @report_format.setter
    def report_format(self, val):
        self._set_single("reports.format", val)

    @property
    def report_emails(self):
        return self._get_list("reports.emails")

    @report_emails.setter
    def report_emails(self, val):
        self._set_list("reports.emails", val, coerce=dataobj.to_uc_lower)

    def get_report_data_for_form(self):
        report_dict = self._get_single("reports", default={})
        return {
                "report_format": report_dict.get("format", ""),     # Empty string --> No report
                "report_emails": list_to_delimited_string(report_dict.get("emails", [])),
            }

    @property
    def in_test(self):
        return self._get_single("in_test", coerce=dataobj.to_bool, default=False)

    @in_test.setter
    def in_test(self, val):
        self._set_single("in_test", val, coerce=dataobj.to_bool)

    @property
    def testing_dict(self):
        test_dict = self._get_single("testing")
        if not test_dict:
            test_dict = self.init_testing()
        return test_dict

    @testing_dict.setter
    def testing_dict(self, val):
        self._set_single("testing", val)

    def init_testing(self):
        """
        Initialise testing dict.
        :return: Nothing
        """
        test_dict = {
            "type": None,
            "start": None,
            "end": None,
            "emails": [],
            "last": None,
            "last_err": None,
            "last_ok": None,
            "num_err": 0,
            "num_ok": 0,
            "num_ok_since_err": 0,
            "route_note": False
        }
        self.testing_dict = test_dict
        return test_dict

    def end_testing(self):
        """
        Set end date and change settings when testing has ended
        :return:
        """
        self.test_end = self.ymd_date_str_from_date_obj(datetime.today())
        self.in_test = False        # Testing not in progress if testing has ended
        self.route_note = False     # Don't want to automatically create & route notifications

    @property
    def test_type(self):
        return self._get_single("testing.type")

    @test_type.setter
    def test_type(self, val):
        self._set_single("testing.type", val)

    @property
    def test_start(self):
        return self._get_single("testing.start")

    @test_start.setter
    def test_start(self, val):
        self._set_single("testing.start", val)

    @property
    def test_end(self):
        return self._get_single("testing.end")

    @test_end.setter
    def test_end(self, val):
        self._set_single("testing.end", val)

    @staticmethod
    def ymd_to_dmy_or_empty(ymd):
        """
        Convert date string of form YYYY-MM-DD into "DD/MM/YYYY" or ""
        :param ymd: Date string - must be in YYYY-MM-DD format
        :return: "DD/MM/YYYY" or ""
        """
        return "/".join(ymd.split("-")[::-1]) if ymd else ""

    @staticmethod
    def ymd_date_str_from_date_obj(date_obj):
        return None if date_obj is None else date_obj.strftime("%Y-%m-%d")

    # @staticmethod
    # def get_date_str_as_date_obj(date_str):
    #     return None if date_str is None else datetime.strptime(date_str, "%Y-%m-%d")
    #
    # def get_test_start_as_date_obj(self):
    #     return self.get_date_str_as_date_obj(self.test_start)
    #
    # def get_test_end_as_date_obj(self):
    #     return self.get_date_str_as_date_obj(self.test_end)

    @property
    def test_emails(self):
        return self._get_list("testing.emails")

    @test_emails.setter
    def test_emails(self, val):
        self._set_list("testing.emails", val, coerce=dataobj.to_uc_lower)

    @property
    def route_note(self):
        return self._get_single("testing.route_note", coerce=dataobj.to_bool, default=False)

    @route_note.setter
    def route_note(self, val):
        self._set_single("testing.route_note", val, coerce=dataobj.to_bool)

    # def get_test_emails_as_string(self):
    #     """
    #     Get test emails as a semicolon separated string.
    #
    #     :return: Test emails string
    #     """
    #     return list_to_delimited_string(self.test_emails)

    def days_since_last_test(self):
        last_test = self.last_test
        if last_test:
            return (datetime.now() - datetime.strptime(last_test, "%Y-%m-%d")).days
        return None

    @property
    def last_test(self):
        return self._get_single("testing.last")
    #
    # @last_test.setter
    # def last_test(self, val):
    #     self._set_single("testing.last", val)
    #
    # @property
    # def last_error(self):
    #     return self._get_single("testing.last_err")
    #
    # @last_error.setter
    # def last_error(self, val):
    #     self._set_single("testing.last_err", val)
    #
    # @property
    # def last_ok(self):
    #     return self._get_single("testing.last_ok")
    #
    # @last_ok.setter
    # def last_ok(self, val):
    #     self._set_single("testing.last_ok", val)
    #
    # @property
    # def num_errors(self):
    #     return self._get_single("testing.num_err")
    #
    # @num_errors.setter
    # def num_errors(self, val):
    #     self._set_single("testing.num_err", val)
    #
    # @property
    # def num_ok(self):
    #     return self._get_single("testing.num_ok")
    #
    # @num_ok.setter
    # def num_ok(self, val):
    #     self._set_single("testing.num_ok", val)
    #
    # @property
    # def num_ok_since_last_error(self):
    #     return self._get_single("testing.num_ok_since_err")
    #
    # @num_ok_since_last_error.setter
    # def num_ok_since_last_error(self, val):
    #     self._set_single("testing.num_ok_since_err", val)

    def get_test_data_dict_for_form(self, with_ymd_dates=False):
        """
        Extracts publisher testing data for use in form
        :param with_ymd_dates: Boolean - True: return dict includes YMD version of dates; False: dates all DMY format.
        :return: dict of data, appropriately formatted
        """
        test_dict = self.testing_dict

        start = self.ymd_to_dmy_or_empty(test_dict.get("start"))
        end = self.ymd_to_dmy_or_empty(test_dict.get("end"))
        ret_dict = {
            "in_test": self.in_test,
            "test_start": start,
            "start_checkbox": start != "",
            "test_end": end,
            "end_checkbox": end != "",
            "test_type": test_dict.get("type"),
            "test_report_emails": list_to_delimited_string(test_dict.get("emails", [])),
            "last_error": self.ymd_to_dmy_or_empty(test_dict.get("last_err")),
            "last_ok": self.ymd_to_dmy_or_empty(test_dict.get("last_ok")),
            "num_err_tests": test_dict.get("num_err") or 0,
            "num_ok_tests": test_dict.get("num_ok") or 0,
            "num_ok_since_last_err": test_dict.get("num_ok_since_err") or 0,
            "route_note_checkbox": test_dict.get("route_note") or False
        }
        if with_ymd_dates:
            ret_dict.update({
                "ymd_test_start": test_dict.get("start") or "",
                "ymd_test_end": test_dict.get("end") or "",
                "ymd_last_error": test_dict.get("last_err") or "",
                "ymd_last_ok": test_dict.get("last_ok") or ""
            })
        return ret_dict


    def update_test_dates_and_stats(self, is_ok, date_obj):
        test_dict = self.testing_dict
        ymd_date_str = self.ymd_date_str_from_date_obj(date_obj)
        test_dict["last"] = ymd_date_str
        if is_ok:
            test_dict["last_ok"] = ymd_date_str
            test_dict["num_ok"] += 1
            test_dict["num_ok_since_err"] += 1
        else:
            test_dict["last_err"] = ymd_date_str
            test_dict["num_err"] += 1
            test_dict["num_ok_since_err"] = 0


class AccOrg(dataobj.DataObj, AccOrgDAO, UserMixin):
    """
    Basic account details for all types of Organisation account user
    {
        "id": "<unique persistent account id - database sequence ID><int>",
        "uuid": "<unique persistent account uuid><string>",
        "created": "<date account created><date>",
        "updated": "<date account last modified><date>",
        "deleted_date": "<date account deleted><date>",
        "live_date": "<date account went live><date>",
        "contact_email": "<Contact email>",
        "tech_contact_emails": ["<List of Technical contact emails>"],
        "api_key": "<api key for api auth><string>",
        "org_name": "<name of an account e.g. for Repository would be Institution name, for Publisher the Publisher name><string>",
        "note": "<general notes for an account><string>" ,
        "role": "<account role, one of 'R', 'P', 'A' (repository/publisher/admin)><string>",
        "status" : "<Repository status, one of: off|okay|problem|failing OR Publisher status, one of: off|okay>",
        "repository_data": SEE RepositoryData for more info,
        "publisher_data": SEE PublisherData for more info
    }
    """
    TECHS = 1
    CONTACT = 2

    mail_account = None
    bcc_addr = None

    def copy(self):
        """
        Create copy of Organisation Account object - used when an account is retrieved via current_user to avoid every call to the
        account using the LocalProxy mechanism
        """
        return deepcopy(self)

    # provider Ids for Harvester or Publisher accounts stored in repository_data.excluded_provider_ids field
    # are prefixed with "h" or "p" to discriminate between them as they may otherwise have conflicting Id values.
    provider_id_template = {True: "h{}", False: "p{}"}

    @property
    def publisher_data(self):
        """
        Returns a PublisherData model, which is a sub model of the Account model, containing methods and data
        pertaining only to Publisher Account users.
        :return: PublisherData model object
        """
        # the data which makes up the PublisherData model is the publisher_data dictionary within an Account's data
        data = self._get_single("publisher_data")
        # if there is no publisher_data dictionary in the current Account, set it as an empty dictionary and return
        # this dictionary instead
        if not data:
            data = {}
            self._set_single("publisher_data", data)
        return PublisherData(data, self)

    @property
    def repository_data(self):
        """
        Returns a RepositoryData model, which is a sub model of the Account model, containing methods and data
        pertaining only to Repository Account users.
        :return: RepositoryData model object
        """
        # the data which makes up the RepositoryData model is the repository_data dictionary within an Account's data
        data = self._get_single("repository_data")
        # if there is no repository_data dictionary in the current Account, set it as an empty dictionary and return
        # this dictionary instead
        if not data:
            data = {}
            self._set_single("repository_data", data)
        return RepositoryData(data, self)

    @property
    def uuid(self):
        return self._get_single("uuid")

    @uuid.setter
    def uuid(self, val):
        self._set_single("uuid", val)

    @property
    def contact_email(self):
        return self._get_single("contact_email")

    @contact_email.setter
    def contact_email(self, val):
        self._set_single("contact_email", val)

    @property
    def tech_contact_emails(self):
        return self._get_list("tech_contact_emails")

    @tech_contact_emails.setter
    def tech_contact_emails(self, val):
        self._set_list("tech_contact_emails", val, coerce=dataobj.to_uc_lower)

    def tech_contact_emails_string(self):
        return list_to_delimited_string(self.tech_contact_emails)

    @property
    def api_key(self):
        return self._get_single("api_key")

    @api_key.setter
    def api_key(self, key):
        self._set_single("api_key", key, coerce=dataobj.to_unicode)

    @property
    def note(self):
        return self._get_single("note")

    @note.setter
    def note(self, val):
        self._set_single("note", val)

    @property
    def raw_role(self):
        """
        Return role code  - One of 'A' (admin), 'P' (publisher), 'R' (repository)
        """
        return self._get_single("role")

    @raw_role.setter
    def raw_role(self, role_char):
        """
        :param role_char: String 'A' (admin), 'P' (publisher), 'R' (repository)
        """
        self._set_single("role", role_char)

    # def has_raw_role(self, roles):
    #     """
    #     :param roles: String - allowed role characters - e.g. "R" (repository) or "PR" -> role one of "P" or "R"
    #     """
    #     return self.raw_role in roles

    @staticmethod
    def translate_raw_role(raw_role):
        return {"A": "admin", "R": "repository", "P": "publisher"}[raw_role]

    @staticmethod
    def role_short_desc(raw_role):
        return {"A": "admin", "R": "repo", "P": "pub"}[raw_role]

    @property
    def is_super(self):
        # Administrator role
        # return self.has_raw_role("A")
        return self.raw_role == "A"

    @property
    def is_repository(self):
        # return self.has_raw_role("R")
        return self.raw_role == "R"

    @property
    def is_publisher(self):
        # return self.has_raw_role("P")
        return self.raw_role == "P"

    def has_role(self, role):
        """
        Original code - uses long format role.
        :param role: String - One of "admin", "repository", "publisher"
        """
        # return self.has_raw_role(role[0].upper())
        return self.raw_role == role[0].upper()


    @property
    def role(self):
        """
        Original code - uses long format role.
        :returns: String - One of "admin", "repository", "publisher"
        """
        return self.translate_raw_role(self.raw_role)

    @role.setter
    def role(self, role):
        """
        Original code - uses long format role.
        :param role: String - One of "admin", "repository", "publisher"
        """
        self.raw_role = role[0].upper()

    def formatted_role(self):
        """
        Formats an account's role for display, also returns an abbreviated string for sorting
        For repository or publisher accounts with no live date, it appends ".test" to the role.

        :return: Tuple (Descriptive-role, Sortable-string-upto-4-chars)
        """
        raw_role = self.raw_role
        role_str = self.translate_raw_role(raw_role)
        sort_str = raw_role
        if raw_role != 'A':
            if not self.has_live_date():
                role_str += ".test"
                sort_str += "T"

            if raw_role == 'P':
                pub_data = self.publisher_data
                if pub_data.in_test:
                    role_str += ".auto"
                    sort_str += "A"
                    if pub_data.route_note:
                        role_str += ".route"
                        sort_str += "R"
        return role_str, sort_str

    @property
    def status(self):
        return self._get_single("status")

    @status.setter
    def status(self, val):
        self._set_single("status", val)

    @property
    def org_name(self):
        return self._get_single("org_name")

    @org_name.setter
    def org_name(self, val):
        self._set_single("org_name", val)

    @property
    def deleted_date(self):
        return self._get_single("deleted_date")

    @deleted_date.setter
    def deleted_date(self, val):
        # a date string of format YYYY-MM-DDTHH:MM:SSZ
        self._set_single("deleted_date", val, coerce=dataobj.date_str())

    @property
    def live_date(self):
        return self._get_single("live_date")

    @live_date.setter
    def live_date(self, val):
        self._set_single("live_date", val)

    def has_live_date(self):
        return self.live_date is not None

    @staticmethod
    def translate_status(status):
        """
        Translate integer status value to text version
        :param status: Int - status value
        :return: String
        """
        return {OFF: "off", OKAY: "okay", FAILING: "failing", PROBLEM: "problem"}.get(status, "off")

    def org_status(self, admin_view=True):
        """
        Returns account status as a string, defaults to "off" if a publisher, and "okay" if a repository
        (in absence of a set value)

        :param admin_view: Boolean - Whether status is for admin view (True) or non-admin view (False)
        :return: String - status value
        """
        status = self.status
        if status is None:
            if self.is_publisher:
                status = OFF
            elif self.is_repository:
                status = OKAY

        str_status = self.translate_status(status)
        if not admin_view:
            # Special case - display "sword paused" instead of "sword failing", otherwise prefix status with "sword "
            str_status = "sword paused" if status == FAILING else "sword " + str_status
        return str_status

    def has_sword_collection(self):
        # indicates if an account has a sword_collection (True or False)
        if self.is_repository:
            return bool(self.repository_data.sword_collection)
        return False

    def has_sword_repo_software(self):
        """
        Returns True if repository software typically uses SWORD for receiving notifications -
        currently Eprints and DSpace.
        :return: Boolean
        """
        repo_sw = self.repository_data.repository_software
        for keyword in ("eprints", "dspace"):
            if keyword in repo_sw:
                return True
        return False

    def tech_and_users_emails_dict_lists(self, role_codes=None):
        """
        Return dict of lists of dicts containing email details of users determined by role_codes parameter string.

        :param role_codes: String - Concatenated User role codes from set:
                {T: Tech contact emails, A: Admin user emails, S: Standard user emails, R: Read-only user emails}
                E.g. "TAS"
                If None, then ALL types are returned
        :return: Dict of lists of dicts
        """
        return AccUser.pull_user_email_details_by_org_id_n_role(
            self.id, role_codes=role_codes, order_ind="role", role_desc=True, return_dict=True
        )

    @classmethod
    def with_sword_activated(cls):
        # returns list of all accounts with a sword collection
        return cls.pull_all(pull_name="sword_active")

    @classmethod
    def get_repositories(cls, live_test_str="LT", repo_status=None):
        """
        Retrieve un-deleted Repositories filtered optionally by Live or Test status, and their operational status
        :param live_test_str: String - "LT": Live OR Test repo; "L": Live repo; "T": Test repo
        :param repo_status: String one of ["on"|"off"|"problem"]
        :return: List of repository account objects from database
        """
        status_map_params = {
            "on": [OKAY, PROBLEM],    # status >= 1 and status <= 3 (i.e. matches any status except OFF)
            "off": [OFF, OFF],              # status >= 0 and status <= 0 (i.e. matches ONLY status OFF)
            "problem": [FAILING, PROBLEM]   # status >= 2 and status <= 3 (i.e. matches only FAILING or PROBLEM)
        }
        default_status_params = [OFF, PROBLEM]     # status >= 0 and status <= 3 (i.e. matches ALL status values)

        # The SQL query defined by pull_name="repo_live_test_status" expects 3 parameters:
        # ['Live-Test' string, lower-status-Integer-value, upper-status-Integer-value]
        # These replace the `?` placeholders in this SQL snippet: INSTR(?, IF(live_date, 'L', 'T')) AND status BETWEEN ? AND ?
        # ISNULL(live_date) returns 0 if live_date is set, or 1 if live_date is NULL.
        params = [live_test_str] + status_map_params.get(repo_status, default_status_params)

        return cls.pull_all(*params, pull_name="repo_live_test_status")

    @classmethod
    def get_active_repo_routing_data_tuples(cls):
        """
        Return list of tuples for Active (i.e. NOT deleted or turned off) repositories.

        This uses 2 queries because attempting to do it in a single bespoke query is too complicated.

        ** We are NOT using `reusable_scroller_obj` here because this function called only once each time Routing
        process occurs - so keeping Scroller cursors & connections open during the intervening period is not justified.

        Each tuple in returned list contains: (repo-id, is-live-boolean, repository-data-object, matching-params-dict)
        """
        # Step 1 - Create a dictionary of Matching params for active (not Off) repo accounts, keyed by match-param ID
        # (which equates to  account ID).
        match_param_scroller = AccRepoMatchParams.scroller_obj(
                pull_name="all_repo_active", rec_format=DICT, scroll_num=REPO_MATCH_PARAM_SCROLL_NUM, end_action=CONN_CLOSE)
        with match_param_scroller:
            active_ac_match_params_dict = {rec_dict["id"]: rec_dict["matching_config"] for rec_dict in match_param_scroller}
        del match_param_scroller    # Delete here to clear down any memory

        # Step 2 - Retrieve Live repo accounts, and create tuple of data to return (using match params from dict)
        ac_scroller = cls.scroller_obj(
            pull_name="repo_active", rec_format=WRAP, scroll_num=REPO_AC_SCROLL_NUM, end_action=CONN_CLOSE)
        with ac_scroller:
            repo_routing_data_list = [
                (repo_acc.id,   # Account ID
                 repo_acc.has_live_date(),  # Boolean - Live or Test indicator
                 repo_acc.repository_data,  # Repository data object
                 # pop() has default `{}` to  allow for remote chance that an Account is turned Off between Steps 1 & 2
                 active_ac_match_params_dict.pop(repo_acc.id, {})  # Matching params dict.
                 ) for repo_acc in ac_scroller
            ]
        return repo_routing_data_list

    @classmethod
    def get_active_repos_with_org_name(cls, get_live=True, org_name=""):
        """
        Return list of LIVE or TEST (those without a Live date) repositories where status is NOT off, which have particular
        org-name (which can contain wildcards ('*' or '%')
        :param get_live: Boolean - True: get Live repos; False: get Test repos
        :param org_name: String - Organisation name (can include wild-card - either '*' or '%')
        """
        # Query 'repo_active_live_or_test_like_orgname' requires 2 parameters in this order:
        # param 1 --> 0: will return Live repos; 1: will return Test repos (this value is matched to result of `ISNULL(live_date)`)
        # param 2 --> org-name string (can include '%' wild cards)
        # Replace any '*' wildcard characters by MySQL '%' wildcard characters
        return cls.pull_all(0 if get_live else 1, org_name.replace("*", "%"), pull_name="repo_active_live_or_test_like_orgname")

    @classmethod
    def get_recent_active_live_org_names_sorted(cls, acc_type="R", limit=None):
        """
        Returns a list of tuples [(acc-id, org-name, live-date), ]

        :param acc_type: String "P"- publisher, "R" - repository
        :param limit: Integer number of records to retrieve
        :return: list of tuples [(acc-id, org-name, live-date), ]
        """
        # No need to use a scroller here as returned records are small, generally < 100 recs returned
        return cls.bespoke_pull(acc_type, pull_name="bspk_org_names_sorted_livedate", limit_offset=limit)

    @classmethod
    def get_org_user_count(cls, org_types=None, on_off=None):
        """
        Returns a list of tuples [(acc-id, org-name, acc-uuid, org-role, org-status, user-count), ] in the order
        specified by order_ind parameter

        :param org_types: String - String of Org-types to match - e.g. "R" or "ARP" etc. or None --> all types
        :param on_off: String - Whether to return On/Off records - e.g. "O" - On Org-ac, "F" - oFf Org-ac,
        :return: list of tuples [(acc-id, org-name, acc-uuid, org-role, org-status-code, user-count), ]
        """
        if not org_types:
            org_types = "ARP"  # All org types  (Admin, Repo, Publisher)
        if not on_off:
            on_off = "OF"    # On & Off
        # No need to use a scroller here as returned records are small, generally < 200 recs returned
        return cls.bespoke_pull(org_types, on_off, pull_name="bspk_org_user_count")

    @classmethod
    def get_publishers(cls, auto_test=None):
        """
        Get list of publisher account objects from database
        :param auto_test: String - None: Ignore auto-test status;
                                   "active": Testing currently in-progress;
                                   "inactive": Testing NOT in progress;
                                   "started": Auto-testing Has a start date (may also have an end-date)
        :return: list of publisher account objects
        """
        map_autotest_to_pull_data = {
            # auto_test value: (pull-name, param-list)
            None: ("undeleted_type", ["P"]),
            "active": ("pub_autotest", ["1", "01"]),    # Field p_in_test is 1, field p_test_start any value
            "inactive": ("pub_autotest", ["0", "01"]),  # Field p_in_test is 0, field p_test_start any value
            "started": ("pub_autotest", ["01", "1"])    # Field p_in_test any value, field p_test_start not-NULL
        }
        pull_name, params = map_autotest_to_pull_data.get(auto_test)
        return cls.pull_all(*params, pull_name=pull_name)

    @classmethod
    def get_test_publisher_ids(cls):
        """
        Get all publisher account IDs which do not yet have a live date (are in "test" status). NOTE this is different
        from publishers being in automated testing mode

        :return: List of Integers (publisher account record ids)
        """
        # bespoke_pull() returns list of record tuples, each tuple contains all fields returned for a record
        # The query defined for "bspk_pub_test_ids" returns just the record id
        # No need to use a scroller here as returned records are small
        return [rec[0] for rec in cls.bespoke_pull(pull_name="bspk_pub_test_ids")]

    @classmethod
    def get_all_undeleted_accounts_of_type(cls, type_str=None, wrap=True, order_by=None, for_update=False):
        """
        :param type_str: String - String of concatenated Role values ('A', 'P', 'R') to return
        :param wrap: Boolean - True: return list of AccOrg objects; False return list of AccOrg data dicts
        :param order_by: String - Order by fields like:
                            "role ASC", "org_name", etc. or None
        :param for_update: Boolean - True: Records may be updated; False records will NOT be updated or deleted
        :return: List of all Undeleted account objects or dicts
        """
        if not type_str:
            type_str = "APR"  # All account types - Admin, Publisher, Repository
        return cls.pull_all(type_str, pull_name="undeleted_type", order_by=order_by, wrap=wrap, for_update=for_update)

    @classmethod
    def get_errors_for_accounts_scroller(cls, pub_or_repo, past_days, min_status):
        """
        Returns a simple scroller (not reusable scroller) for retrieving errors for accounts.

        :param pub_or_repo: String - One of [all|publisher|repository]
        :param past_days: String - Number of days
        :param min_status: Int - minimum status
        :return: List of tuples [(acc_id, acc_uuid, api_key, org_name, live_or_test-string, contact_email, acc-status, err_date, err_msg, err_id, err_emailed-boolean)] ORDERED BY org_name, err_date
        """
        # Scroller returns RAW records.  It's connection & cursor will be deleted after use (relatively infrequent use,
        # by one of admin screens doesn't justify holding connection open)
        return cls.scroller_obj(min_status, past_days, pull_name=f"bspk_problems_{pub_or_repo}",
                                    scroll_num=AC_ERRORS_SCROLL_NUM, rec_format=RAW, end_action=CONN_CLOSE)

    @classmethod
    def pull_by_api_key(cls, api_key):
        """
        :return: Account object for specified api-key
        """
        return cls.pull(api_key, pull_name="apikey")

    @classmethod
    def pull_by_contact_email(cls, contact_email):
        """
        :return: Account object corresponding to contact-emaoil
        """
        return cls.pull(contact_email, pull_name="contact")

    def remove_unix_ftp_account(self):
        """
        Removes UNIX account (does NOT update database).
        """
        if self.is_publisher:
            # Unix user name is the same as the UUID
            user_id = self.uuid
            result = run_script_return_err_code(full_script_path("deleteFTPuser.sh"), user_id)
            snippet = f"UNIX account '{user_id}' ({self.org_name})"
            if result == 0:
                current_app.logger.info(f"Removed {snippet}")
            else:
                current_app.logger.log(ERROR_X, f"Failed to remove {snippet} - Error code: {result}")

    def create_ftp_account(self):
        """
        create_ftp_account - creates a UNIX ftp user account (for Publishers)
        :return:
        """
        # create an FTP user for the account, if it is a publisher
        # TODO / NOTE: if the service has to be scaled up to run on multiple machines,
        # the ftp users should only be created on the machine that the ftp address points to.
        # so the create user scripts should be triggered on that machine. Alternatively the user
        # accounts could be created on every machine - but that leaves more potential security holes.
        # Better to restrict the ftp upload to one machine that is configured to accept them. Then
        # when it runs the schedule, it will check the ftp folder locations and send any to the API
        # endpoints, so the heavy lifting would still be distributed across machines.
        # un = self.data['email'].replace('@','_')
        user_id = self.uuid

        result = run_script_return_err_code(full_script_path("createFTPuser.sh"), user_id, self.api_key)
        snippet = f"UNIX FTP account '{user_id}' ({self.org_name})"
        if result == 0:
            current_app.logger.info(f"Created {snippet}")
        else:
            err_msg = f"Failed to create {snippet} - Error code: {result}"
            current_app.logger.log(ERROR_X, err_msg)
            raise Exception(err_msg)

    # @classmethod
    # def all_repo_pkids(cls):
    #     """
    #     :return:
    #     """
    #     return [rec[0] for rec in cls.bespoke_pull("repository", pull_name="bspk_acc_ids")]

    @classmethod
    def num_repositories(cls):
        """
        Returns the number of undeleted repositories.

        NOTE that this is less efficient than using `cls.count(pull_name="bspk_repo_ac_ids_providers")` as it pulls back
        rows of data and then calculates length - BUT it is only used in 1 place for Harvester GUI - so not a problem.
        If `cls.count(pull_name="bspk_repo_ac_ids_providers")` was used then it would create an additional cursor, which
        isn't justified.

        :return: Integer - number of repositories
        """
        return len(cls.bespoke_pull(pull_name="bspk_repo_ac_ids_providers"))

    @classmethod
    def get_account_id_to_org_names_dict(cls, acc_type, live_test="L", close_cursor=False):
        """
        Returns a dict mapping {account-id: "account-org-name", }

        :param acc_type: String "P"- publisher, "R" - repository, "PR" - both publisher & repository
        :param live_test: String "T" (Test repos), "L" (Live repos) or "TL" (Live & Test repos)
        :param close_cursor: Boolean - True: close cursor after use [specify this if function is called infrequently];
                                       False: Leave cursor in existence (use this if expect to call function repeatedly)
        :return: dict of integer-ids mapped to org-name  { int-id: "org-name", ... }
        """
        # No need to use a scroller here as returned records are small, generally < 100 recs returned
        return {id_: org_name for id_, org_name in
                cls.bespoke_pull(acc_type, live_test, pull_name="bspk_org_names", close_cursor=close_cursor)}

    @classmethod
    def repo_ids_using_provider_or_not(cls, provider_id, using=True, for_update=False, is_harvester=True):
        """
        Returns list of pkids of those repositories that are either Using or NOT Using a provider
        :param provider_id: ID of the provider
        :param using: Boolean - True: Return IDs of repos that are using a provider;
                                False: Return IDS of repos NOT using provider
        :param for_update: Boolean - True: SELECT SQL includes " FOR UPDATE" clause; False: Normal SELECT stmt
        :param is_harvester: Boolean - True: Provider is a harvester account; False: Provider is a Publisher account
        :return: List of (id, org-name, provider_ids) tuples
        """
        result_list = []
        provider_id = cls.provider_id_template[is_harvester].format(provider_id)
        # No need to use a scroller here as returned records are small, generally < 100 recs returned
        for repo_id, org_name, str_list_provider_ids in cls.bespoke_pull(pull_name="bspk_repo_ac_ids_providers",
                                                                         for_update=for_update):
            # Convert the 'stringified' list back into a list
            provider_ids = AccOrgDAO.str_to_list(str_list_provider_ids)
            # If repo is using the provider, then provider_id should NOT appear in the provider_ids list
            if using == (not provider_id in provider_ids):
                result_list.append((repo_id, org_name, provider_ids))
        return result_list

    @classmethod
    def num_repositories_using_provider(cls, provider_id, is_harvester=True):
        """
        Returns the number of repositories (excluding those deleted) that are configured to receive notifications
        from a provider (identified by provider_id).

        (A repository will receive notifications if the provider_id does NOT appear in the excluded_provider_ids list).

        :param provider_id: Id of provider
        :param is_harvester: Boolean - True: Provider is a harvester account; False: Provider is a Publisher account
        :return: Integer - number of repositories
        """
        return len(cls.repo_ids_using_provider_or_not(provider_id, using=True, is_harvester=is_harvester))

    @classmethod
    def select_or_deselect_provider_from_all_repos(cls, provider_id, select, provider_name=None, is_harvester=True):
        """
        Either removes (selects) or adds (deselects) supplied provider_id (a publisher or harvester webservice) to
        the excluded_provider_ids list.

        Creates a log output INFO msg if provider_name is not None.

        :param provider_id: Id of the harvester webservice or publisher
        :param select: Boolean - True: remove from excluded list; False: add to excluded list
        :param provider_name: String - None or name of provider (if None then there will be NO log output)
        :param is_harvester: Boolean - True: Provider is a harvester account; False: Provider is a Publisher account
        :return: number of repositories  changed

        """
        result_list = cls.repo_ids_using_provider_or_not(
            provider_id, using=not select, for_update=True, is_harvester=is_harvester)

        provider_id = cls.provider_id_template[is_harvester].format(provider_id)
        count = 0
        log_msgs = []
        for id, org_name, excluded_providers in result_list:
            if provider_name:
                log_msgs.append(f"  {id}: '{org_name}'")
            if select:
                excluded_providers.remove(provider_id)
            else:
                excluded_providers.append(provider_id)
            num_changed = cls.bespoke_update(id,
                                             data_vals=[AccOrgDAO.list_to_str(excluded_providers)],
                                             query_name="update_repo_providers",
                                             commit=False)
            count += num_changed

        cls.commit()
        if provider_name and count:
            msg = "Notification source: '{}' (id: {}) has been {} for {} repository accounts (where it was previously {}):\n{}\n"
            current_app.logger.info(msg.format(provider_name,
                                               provider_id,
                                               "SELECTED" if select else "DE-SELECTED",
                                               count,
                                               "de-selected" if select else "selected",
                                               ",\n".join(log_msgs)))
        return count

    def send_email(self, subject, msg, to, email_template=None, save_acc_email_rec=False, **kwargs):
        """
        Send email
        :param subject: String - Email subject line
        :param msg: String - Email message
        :param to: Int CODE indicating type of email addresses to use:
                        TECHS --> Use Technical Contact emails, if they exist otherwise Contact email
                        CONTACT --> Use Contact email
                   or LIST of email addresses to use
        :param email_template:
        :param kwargs:
        :return: Tuple (mail_to_list or None, cc_list or None)
        """
        if AccOrg.mail_account is None:
            AccOrg.mail_account = MailAccount()
            AccOrg.bcc_addr = current_app.config.get("SUPPORT_EMAIL_ACS")
        _contact_email = self.contact_email
        contact_list = [_contact_email] if _contact_email else None
        mail_to_list = cc_list = None
        if to == self.TECHS:
            mail_to_list = self.tech_contact_emails
            # If Tech contacts exist, then add Contact email in CC
            if mail_to_list:
                cc_list = contact_list
            else:   # No tech contacts, so default to Contact email
                mail_to_list = contact_list
        elif to == self.CONTACT:
            mail_to_list = contact_list
        elif isinstance(list, to):
            mail_to_list = to
            cc_list = contact_list

        if mail_to_list and email_template:
            env_name = environment_name()
            env_name = "" if env_name == "Live" else env_name + " "
            email_msg = MailMsg(f"{env_name}{subject}", email_template, msg=msg, environment=env_name, **kwargs)
            current_app.logger.debug(f"EMAIL Subject: '{email_msg._subject}'\nBody: |{email_msg.text}|\nTo: {mail_to_list}, CC: {cc_list}")
            AccOrg.mail_account.send_mail(
                mail_to_list,
                cc=cc_list,
                bcc=AccOrg.bcc_addr,
                msg_obj=email_msg
            )
            if save_acc_email_rec:
                # If wanted, save the email (associate it with the Account)
                json_dict = {
                    "acc_id": self.id,
                    "to_addr": "; ".join(mail_to_list),
                    "subject": subject,
                    "body": msg,
                    "status": None,
                    "err_ids":[]
                }
                if cc_list:
                    json_dict["cc_addr"] = "; ".join(cc_list)
                AccNotesEmails(json_dict).insert_email()
        return mail_to_list, cc_list


class AccUser(dataobj.DataObj, AccUserDAO, UserMixin):
    """
    Basic details for each account user - stored as a dict in the self.data
    self.data:
    {
        "id": "<unique persistent account id - database sequence ID><int>",
        "created": "<date account created><date>",
        "last_success": "<date account last successfully logged into>",
        "last_failed": "<date account last failure to log in>",
        "deleted_date": "<date account deleted><date>",
        "uuid": "<unique persistent User account uuid><string>",
        "acc_id": "<Foreign key to Organisation Account record (to which this user belongs)>",
        "username": "<Username - usually an email address>",
        "user_email": "<Contact email - used where username is NOT an email address>",
        "surname": "<User surname><string>",
        "forename": "<User forename(s)><string>",
        "org_role": "<Role of user within their organisation><string>",
        "role_code": "<1 Char code indicating Router role, one of: R,S,A,J,D,K><string>",
        "password": "<hashed password for ui login><string>",
        "failed_login_count": "Integer count of successive failed login attempts",
        "direct_login" : "Boolean - indicates if user can login directly, bypassing need for emailed access code",
        "reset_token": {
            "expiry": "<date>",
            "token": "<token>"
        },
        "login_token": {
            "expiry": "<date>",
            "token": "<token>",     # Login token value
            "remember": <Boolean>,  # Indicates whether user clicked "Stay logged in" checkbox
            "cookie": <cookie value>    # Login cookie sent to user's browser when login-link token is emailed
        },
        # "last_one_time_msg": "<YYYY-MM-DD date of last one-time message displayed to user"
        # Used to preset users with information e.g. about need to press Shift-F5 to reload stuff after a release
    }

    In addition, the AccUser object includes the parent Organisation Account - but this is NOT attached to self.data as
    it is NOT to be saved in AccUser (acc_user) data records.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.acc_org = None     # Parent Organisation Account object

    def copy(self):
        """
        Create copy of AccUser object - used when an account is retrieved via current_user to avoid every call to the
        account using the LocalProxy mechanism
        """
        return deepcopy(self)

    @property
    def uuid(self):
        return self._get_single("uuid")

    @uuid.setter
    def uuid(self, val):
        self._set_single("uuid", val)

    @property
    def org_id(self):
        return self._get_single("acc_id")

    @org_id.setter
    def org_id(self, val):
        self._set_single("acc_id", val)

    @property
    def username(self):
        return self._get_single("username")

    @username.setter
    def username(self, val):
        self._set_single("username", val)

    @property
    def user_email(self):
        return self._get_single("user_email", default="")

    @user_email.setter
    def user_email(self, val):
        self._set_single("user_email", val)

    def get_email(self):
        """
        Note that user_email is only populated when username is NOT an email address
        :return: User's email address
        """
        return self.user_email or self.username

    @property
    def surname(self):
        return self._get_single("surname", default="")

    @surname.setter
    def surname(self, val):
        self._set_single("surname", val)

    @property
    def forename(self):
        return self._get_single("forename", default="")

    @forename.setter
    def forename(self, val):
        self._set_single("forename", val)

    @property
    def hashed_password(self):
        return self._get_single("password")

    @hashed_password.setter
    def hashed_password(self, val):
        self._set_single("password", val)

    def set_password(self, password):
        # hashes and sets the password
        self._set_single("password", generate_password_hash(password))

    def check_password(self, password):
        # returns True if hashed password matches that provided
        existing = self.hashed_password
        if existing is None:
            return False
        return check_password_hash(existing, password)

    def clear_password(self):
        self._delete("password")

    @property
    def note(self):
        return self._get_single("note")

    @note.setter
    def note(self, val):
        self._set_single("note", val)

    @property
    def role_code(self):
        """
        Return role code  - One of 'R' (read-only user), 'S' (standard user), 'A' (admin), 'K' (API-key user), 'J' (jisc admin), 'D' (developer admin)
        """
        return self._get_single("role_code")

    @role_code.setter
    def role_code(self, role_char):
        """
        :param role_char: String - See role_code func above for possible values
        """
        self._set_single("role_code", role_char)

    def has_role(self, roles):
        """
        :param roles: String - allowed role characters - e.g. "B" (basic user) or "JD" -> role one of "J" or "D"
        """
        return self.role_code in roles

    @staticmethod
    def translate_raw_role(raw_role, full=True):
        """
        Translate single char User Role code to either Full or Short description
        :param raw_role: Char - role code
        :param full: Boolean - True: Full description; False: Short description
        :return: String - description
        """
        if full:
            desc = {"S": "Standard", "A": "Organisation Admin", "R": "Read-only", "J": "Jisc Admin", "D": "Jisc Developer", "K": "API-key"}.get(raw_role)
        else:
            desc = {"S": "Standard", "A": "Org admin", "R": "Read-only", "J": "Jisc admin", "D": "Developer", "K": "API-key"}.get(raw_role)
        return desc or "UNSPECIFIED"

    @property
    def role_desc(self):
        return self.translate_raw_role(self.role_code)

    @property
    def role_short_desc(self):
        return self.translate_raw_role(self.role_code, False)

    @property
    def is_read_only(self):
        return self.has_role("RK")

    # @property
    # def is_std_user(self):
    #     return self.has_role("S")

    @property
    def is_org_admin(self):
        # Administrator role
        return self.has_role("A")

    @property
    def is_jisc_admin(self):
        # Jisc Administrator or Developer role
        return self.has_role("JD")

    @property
    def is_developer(self):
        # Administrator or Developer role
        return self.has_role("D")

    @property
    def is_admin(self):
        return self.has_role("AJD")

    @property
    def is_api(self):
        return self.has_role("K")

    @property
    def org_role(self):
        return self._get_single("org_role")

    @org_role.setter
    def org_role(self, val):
        self._set_single("org_role", val)

    @property
    def deleted_date(self):
        return self._get_single("deleted")

    @deleted_date.setter
    def deleted_date(self, val):
        # a date string of format YYYY-MM-DDTHH:MM:SSZ
        self._set_single("deleted", val, coerce=dataobj.date_str())

    @property
    def last_login_datetime_str(self):
        """
        Returns datetime string in form: "YYYY-MM-DD HH:MM:SS"
        """
        return self.reformat_datetime_str(self._get_single("last_success"), True)

    @property
    def last_login_datetime(self):
        """
        Returns datetime object
        """
        return self._get_single("last_success", coerce=dataobj.to_datetime_obj("%Y-%m-%dT%H:%M:%SZ"))

    @last_login_datetime.setter
    def last_login_datetime(self, val):
        """
        Saves datetime object (as "%Y-%m-%dT%H:%M:%SZ" format string)
        """
        self._set_single("last_success", val, coerce=dates.format)

    @property
    def last_failed_login_datetime_str(self):
        """
        Returns datetime string in form: "YYYY-MM-DD HH:MM:SS"
        """
        return self.reformat_datetime_str(self._get_single("last_failed"), True)

    @property
    def last_failed_login_datetime(self):
        """
        Returns datetime object
        """
        return self._get_single("last_failed", coerce=dataobj.to_datetime_obj("%Y-%m-%dT%H:%M:%SZ"))

    @last_failed_login_datetime.setter
    def last_failed_login_datetime(self, val):
        """
        Saves datetime object (as "%Y-%m-%dT%H:%M:%SZ" format string)
        """
        self._set_single("last_failed", val, coerce=dates.format)

    @property
    def failed_login_count(self):
        return self._get_single("failed_login_count", default=0)

    @failed_login_count.setter
    def failed_login_count(self, val):
        self._set_single("failed_login_count", val)

    def create_token(self, field_path, lifetime_dict, token_value, extra_dict=None):
        """
        Create a token object.
        :param field_path: String - dot.name of field that holds token, e.g "reset_token" or "login_token"
        :param lifetime_dict: Dict - for passing to `relativedelta`, like {"weeks": 1} or {"minutes": 30}
        :param token_value: String - Token value
        :param extra_dict: OPTIONAL dict - will be merged with returned dict if provided
        :return: Dict containing at least the first 2 elements shown here:
                {"expiry": date-time-isoformat-string,
                 "value": UUID,
                 ... - Plus any additional elements from extra_dict
                }
        """
        token_obj = {
            "expiry": (datetime.today() + relativedelta(**lifetime_dict)).isoformat(),
            "value": token_value
        }
        if extra_dict:
            token_obj.update(extra_dict)

        self._set_single(field_path, token_obj)
        return token_obj

    def get_check_token(self, field_path):
        """
        Get a reset  if there is one available, and make sure it is valid.

        If the token has passed expiry time, remove the token and return None.

        :return: token dict - looks like {
            "expiry": "<date>",
            "value": "<uuid>",
            "remember": <Boolean>  - OPTIONAL dict element

        }
        """
        token = self._get_single(field_path)
        if token:
            # Check if token has expired
            if datetime.fromisoformat(token["expiry"]) < datetime.today():
                self._set_single(field_path, None)
                token = None
        return token

    @property
    def reset_token(self):
        """
        Get a reset token if there is one available.

        :return: Reset token part of account - looks like {
            "expiry": "<date>",
            "value": "<uuid>"
        }
        """
        return self._get_single("reset_token")

    @reset_token.setter
    def reset_token(self, value):
        """
        Setter for reset token.

        Should either be an empty dictionary when set, or like {
            "expiry": "<date>",
            "value": "<uuid>"
        }
        """
        self._set_single("reset_token", value)

    def valid_reset_token(self):
        """
        Get a reset token if there is one available, and make sure it is valid.

        If the token has passed expiry, remove the token and return None.

        :return: Reset token part of account - looks like {
            "expiry": "<date>",
            "value": "<uuid>"
        }
        """
        return self.get_check_token("reset_token")

    def create_reset_token(self):
        """
        Create a reset token and then add it to the account object. Also, return it as it will need to be used
        immediately after creation.
        """
        return self.create_token("reset_token", {"weeks": 1}, self.create_uuid())

    @property
    def login_token(self):
        """
        Get a access code if there is one available.

        :return: access code - looks like {
            "expiry": "<date>",
            "value": "<uuid>",
            "remember": <Boolean>,
            "cookie": <cookie value>
        }
        """
        return self._get_single("login_token")

    @login_token.setter
    def login_token(self, value):
        """
        Setter for access code.

        Should either be an empty dictionary when set, or like {
            "expiry": "<date>",
            "value": "<uuid>",
            "remember": <Boolean>,
            "cookie": <cookie value>
        }
        """
        self._set_single("login_token", value)

    def valid_login_token(self):
        """
        Get a access code if there is one available, and make sure it is valid.

        If the token has passed expiry, remove the token and return None.

        :return: access code - looks like {
            "expiry": "<date>",
            "value": "<uuid>",
            "remember": <Boolean>
        }
        """
        return self.get_check_token("login_token")

    def create_login_token_n_cookie(self, remember=False):
        """
        Create a access code (valid for 5 minutes), together with `remember` indicator & cookie and then add it to
        the account object. Also, return it as it will
        need to be used immediately after creation.
        """
        return self.create_token("login_token",
                                 {"minutes": 5},
                                 str(randint(100000,999999)),   # Generate random 6 digit string
                                 {"remember": remember, "cookie": self.create_uuid()}
                                 )

    @property
    def direct_login(self):
        return self._get_single("direct_login")

    @direct_login.setter
    def direct_login(self, val):
        self._set_single("direct_login", val)

    @staticmethod
    def create_uuid():
        return uuid.uuid4().hex

    # @property
    # def last_one_time_msg(self):
    #     return self._get_single("last_one_time_msg")
    #
    # @last_one_time_msg.setter
    # def last_one_time_msg(self, val):
    #     self._set_single("last_one_time_msg", val)

    @classmethod
    def pull_user_acs(cls, org_id, role_codes=None, inc_deleted=False, order_by=None, for_update=False):
        """
        Get list of User account objects from database (do NOT retrieve their parent Organisation recs)
        :param org_id: Integer - ID of Account to which users belong
        :param role_codes: String - String of Role-codes to match - e.g. "S" or "JD" etc or None: pull all
        :param inc_deleted: Boolean - True: Include deleted records, False: Exclude deleted records
        :param order_by: String - Order by fields like:
                            "id DESC", "username ASC", "role_code DESC", "role_code ASC, username DESC" or None
        :param for_update: Boolean - True: expect to update records; False: read-only
        :return: list of User account objects
        """
        if role_codes is None:
            pull_name = "all_undeleted_4_acc"
            args = [org_id]
        else:
            pull_name = "all_of_type_4_acc"
            args = [org_id, role_codes, inc_deleted]
        return cls.pull_all(*args, pull_name=pull_name, order_by=order_by, for_update=for_update)

    @classmethod
    def pull_by_username(cls, username, for_update=False):
        """
        :return: AccUser object for specified user
        """
        return cls.pull(username, pull_name='active_user', for_update=for_update)

    @classmethod
    def pull_user_n_org_ac(cls, key, pull_name_suffix):
        """
        Retrieve User Account record and its "parent" Organisation Account record,
        return AccUser object which contains AccOrg object.

        @param key: key for retrieving record
        @param pull_name_suffix: Suffix of pull_name for query -
                                 MUST BE ONE OF: "user_id", "username", "user_uuid"
        @return: AccUser object for specified user or None
        """
        # The rec_tuple returned by this bespoke JOIN query, comprises both acc_user and account record data
        rec_tuple_list = cls.bespoke_pull(key, pull_name=f"bspk_user_n_org_ac_recs_by_{pull_name_suffix}")
        if rec_tuple_list:
            rec_tuple = rec_tuple_list[0]   # Expect a single record to have been returned
            # Create AccUser object for the acc_user record data (first 12 fields)
            acc_user = AccUser(cls.recreate_json_dict_from_rec(rec_tuple[:12]))
             # AccOrg object is created from remaining record data fields
            AccOrg.set_all_cols()   # Need to do this recreate_json_dict_from_rec() works recreate_
            acc_user.acc_org = AccOrg(AccOrg.recreate_json_dict_from_rec(rec_tuple[12:]))
            return acc_user

        return None
        # THIS IS AN ALTERNATIVE MECHANISM FOR OBTAINING acc_user Object via 2 DB SELECTS
        # acc_user = cls.pull(acc_user_id)
        # if acc_user:
        #     acc_org = AccOrg.pull(acc_user.org_id)
        #     if acc_org is None:
        #         raise Exception(f"Expected Parent Organisation Account record with ID: '{acc_user.org_id}' NOT found.")
        #     acc_user.acc_org = acc_org
        # return acc_user


    @classmethod
    def pull_all_user_n_org_accounts(cls, org_types=None, live_test=None, role_codes=None, del_on_off=None, list_func=None):
        """
        Retrieve User Account records together with their "parent" Organisation Account records,
        return List of AccUser objects (each of which contains parent AccOrg object) OR a list of data lists
        (if `list_func` is passed).

        :param org_types: String - String of Org-types to match - e.g. "R" or "ARP" etc. or None --> all types
        :param live_test: String - String of characters indicating if Live &/or Test Orgs are required - "L" or "T" or "LT" etc. or None --> "LT"
        :param role_codes: String - String of User Role-codes to match - e.g. "S" or "JD" etc. or None --> all types
        :param del_on_off: String - Whether to return Deleted/On/Off records - e.g. "O" - On Org-ac, "F" - oFf Org-ac, "D" - Deleted User-ac
        :param list_func: Function - A function taking 1 argument (AccUser) that returns a list of values to append
                to returned data list

        :return: List of AccUser objects for specified Organisation OR
                 a List of lists of data extracted from AccUser objects
                 (depending on whether list_func is provided)
        """
        acc_list = []
        if not org_types:
            org_types = "ARP"  # All org types  (Admin, Repo, Publisher)
        if not live_test:
            live_test = "LT"  # Both Live & Test orgs
        if not role_codes:
            role_codes = "SRAJD"    # All user roles
        if not del_on_off:
            del_on_off = "O"    # On
        rec_tuple_list = cls.bespoke_pull(org_types, live_test, role_codes, del_on_off, pull_name="bspk_all_user_n_org_ac_recs")
        if rec_tuple_list:
            AccOrg.set_all_cols()  # Need to do this recreate_json_dict_from_rec() works recreate_

            for rec_tuple in rec_tuple_list:
                # Create AccUser object for the acc_user record data (first 12 fields)
                acc_user = AccUser(cls.recreate_json_dict_from_rec(rec_tuple[:12]))
                # AccOrg object is created from remaining record data fields
                acc_user.acc_org = AccOrg(AccOrg.recreate_json_dict_from_rec(rec_tuple[12:]))
                # Either append list of extracted data (if `list_func` is specified) or the acc_user object
                acc_list.append(list_func(acc_user) if list_func else acc_user)
        return acc_list


    @classmethod
    def _return_dict_or_list_of_user_emails_roles_org_ids(cls, rec_tuple_list, role_desc, return_dict):
        """
        Return EITHER a DICT keyed by Org-Id of Lists of Tuples (User-role-code or role-short-description, Email)
        {
            Org-Id: { "role-desc-1": ["email-addr", ...], "role-desc-2": ["email-addr", ...],  ...}
        }
        OR a List of Tuples (Org-Id, User-role-code or role-short-description, Email).

        :param rec_tuple_list: Raw result of bespoke database query - Data order by Org-Id, User-role-code
        :param role_desc: Boolean - True: Role short-description is used, False/None: role code character is used
        :param return_dict: Boolean - True: return Dict of lists of dicts; False: Return list of dicts
        :return: EITHER Dict [keyed by Org-Id] of lists of tuples [(user-role, email), ...]
                 OR List of tuples [(Org-id, user-role, email), ...]
        """
        def translate(role):
            return cls.translate_raw_role(role, full=False)

        def raw(role):
            return role

        convert_role = translate if role_desc else raw

        if return_dict:
            ret_dict = {}
            last_id = role_email_dict = None
            for org_id, role, email in rec_tuple_list:
                if org_id != last_id:
                    if last_id:
                        ret_dict[last_id] = role_email_dict
                    role_email_dict = {}
                    last_id = org_id

                role = convert_role(role)
                try:
                    role_email_dict[role].append(email)
                except KeyError:
                    role_email_dict[role] = [email]
            if last_id:
                ret_dict[last_id] = role_email_dict

            return ret_dict
        else:
            return [(org_id, convert_role(role), email) for org_id, role, email in rec_tuple_list]

    @classmethod
    def pull_user_emails_roles_org_ids_by_role_n_org_type(cls, org_role, role_codes=None, role_desc=True, return_dict=True):
        """
        Retrieve Email addresses & user-role & org-id for All organisations of specified org-type (org role), usually
        "R" or "P" or both "RP", and their users with specified roles.

        Return EITHER a DICT keyed by Org-Id of Dict keyed by user role (User-role-code or role-short-description of
        Lists of Emails
        OR a List of Tuples (Org-Id, User-role-code or role-short-description, Email).

        :param org_role: String - Org Account role codes required - usually "R", "P" or "RP" (for both Repo & Publisher)
        :param role_codes: String - Specifies the user roles of interest: Concatenated characters from set: {S, R, A, J, D} (emails of users with these roles will be returned)
        :param role_desc: Boolean - True: Return role short-descriptions, False/None: Return role code characters
        :param return_dict: Boolean - True: Return Dict of lists of dicts; False: Return list of dicts
        :return: EITHER Dict [keyed by Org-Id] of lists of tuples [(user-role, email), ...]
                 OR List of tuples [(Org-id, user-role, email), ...]
        """
        if not role_codes:
            role_codes = "SRAJD"    # All user roles

        return cls._return_dict_or_list_of_user_emails_roles_org_ids(
            # Data retrieved ordered by Org-Id, User-role-code
            cls.bespoke_pull(role_codes, org_role, pull_name="bspk_org_id_user_role_username_email_for_role_n_org_type"),
            role_desc, return_dict
        )

    @classmethod
    def pull_user_emails_roles_org_ids_by_role_n_org_ids(cls, org_ids, role_codes=None, role_desc=True, return_dict=True):
        """
        Retrieve Email addresses & user-role & org-id for All organisations with specified IDs and their users with
        specified roles.

        Return EITHER a DICT keyed by Org-Id of Dict keyed by user role (User-role-code or role-short-description of
        Lists of Emails
        OR a List of Tuples (Org-Id, User-role-code or role-short-description, Email).

        :param org_ids: EITHER List of Int Org-IDs OR CSV string of Org-IDs (no spaces) - IDs of Organisations
                        for which users email addresses (usernames) are required
        :param role_codes: String - Specifies the user roles of interest (emails of users with these roles will be returned)
        :param role_desc: Boolean - True: Role short-description is used, False/None: role code character is used
        :param return_dict: Boolean - True: return Dict of lists of dicts; False: Return list of dicts
        :return: EITHER Dict [keyed by Org-Id] of lists of tuples [(user-role, email), ...]
                 OR List of tuples [(Org-id, user-role, email), ...]
        """
        if not role_codes:
            role_codes = "SRAJD"    # All user roles
        if isinstance(org_ids, list):
            org_ids = ",".join(org_ids)

        return cls._return_dict_or_list_of_user_emails_roles_org_ids(
            # Data retrieved ordered by Org-Id, User-role-code
            cls.bespoke_pull(role_codes, org_ids, pull_name="bspk_org_id_user_role_username_email_for_role_n_org_ids"),
            role_desc, return_dict
        )

    @classmethod
    def pull_user_email_details_by_org_id_n_role(cls, org_id, role_codes=None, order_ind="role", role_desc=True, return_dict=True):
        """
        Return EITHER a DICT keyed by role (code or short-description) with each element being a List of dicts I.E.:
            { "role-code-or-desc": [{"email": ..., "name": ..., "org_role": users-org-role}, {...}. ...], ... }

        OR a LIST of dicts I.E.:
            [{"email": ..., "name": ..., "role": code-or-description, "org_role": users-org-role}, {...}. ...]

        :param org_id: Id of Org account
        :param role_codes: String containing required role code chars (if None, then all roles are returned)
        :param order_ind: String - Order By snippet - OPTIONS: None, "username", "role.username", "role"
        :param role_desc: Boolean - True: Role short-description is used, False/None: role code character is used
        :param return_dict: Boolean - True: return Dict of lists of dicts; False: Return list of dicts
        :return: Dict of lists of dicts {"r": [{...}, ...], ...} OR List of dicts [{...},...]
        """
        order_by = {
            "username": "username ASC",
            "role.username": "role_code ASC, username ASC",
            "role": "role_code ASC"
        }.get(order_ind)
        org_users_list = cls.pull_user_acs(org_id, role_codes, order_by=order_by)
        if return_dict:
            ret_dict = {}
            for user_ac in org_users_list:
                role = user_ac.role_short_desc if role_desc else user_ac.role_code
                details_dict = {
                    "email": user_ac.get_email(),
                    "name": user_ac.forename + " " + user_ac.surname,
                    "org_role": user_ac.org_role
                }
                try:     # Assume role key already exists in dict
                    ret_dict[role].append(details_dict)
                except KeyError:    # First time a particular role is encountered
                    ret_dict[role] = [details_dict]
            return ret_dict
        else:
            return [
                {
                    "email": user_ac.get_email(),
                    "name": user_ac.forename + " " + user_ac.surname,
                    "role": user_ac.role_short_desc if role_desc else user_ac.role_code,
                    "org_role": user_ac.org_role
                } for user_ac in org_users_list
            ]


class AccBulkEmail(AccBulkEmailDAO):
    """
    Class for Bulk email

    """
    @classmethod
    def list_email_dicts(cls, limit=None, ac_type=None, status=None):
        """
        Retrieve notes &/or ToTos &/or email messages related to particular accounts, & which have specified
        status (None, Highlighted, Resolved, Deleted).
        These items are returned from `acc_notes_emails` and, for bulk-emails, the `acc_bulk_email` table via
        a single bespoke SQL query involvig`acc_notes_email LEFT JOIN acc_bulk_email` that retrieves
        `subject` & `body` fields from acc_bulk_email where they exist.

        :param limit: Number - Maximum number of records to retrieve; or empty string or None if ALL recs reqd
        :param ac_type: None or String - Types of record to return:
                            "A" (All - Pub & Repo), "P" (Publishers), "R" (Repos)
        :param status: None or String - Single status or concatenated string of statuses of records to return:
                            "N" (Null status), "H" (Highlighted), "R" (Resolved),  "D" (Deleted) or any combination
                            (e.g. "HNR").

        :return: List of record dicts
        """
        def recreate_dict_bspk(rec_tuple):
            """
            :param rec_tuple: Tuple containing `acc_group_email` record fields PLUS the orgs derived from
                              joined `account` records
            """
            # Recreate the acc_group_email record from the base data (all except last org field in rec_tuple)
            rec_dict = cls.recreate_json_dict_from_rec(rec_tuple[:-1])
            rec_dict["orgs"] = rec_tuple[-1]
            return rec_dict

        limit = int(limit) if limit else None
        if not ac_type:
            ac_type = "APR"  # A=All (Publisher & Repository); P=Publisher; R=Repository
        if not status:
            status = "HNR"   # Not deleted
        return [
            recreate_dict_bspk(rec_tuple) for rec_tuple
            in cls.bespoke_pull(status, ac_type, pull_name="bspk_emails", limit_offset=limit)
        ]

    @classmethod
    def update_status(cls, rec_id=None, status=None):
        """
        Update status indicator for specified rec ID.

        :param rec_id: Id of record to update
        :param status: String - "R" (Resolved), "H" (Highlight), "D" (Delete), "" (Remove highlight)

        :return: Integer - Number of records affected
        """
        if status in ("", "N"):
            status = None   # causes NULL to be set in database
        return cls.bespoke_update(status, rec_id, query_name="update_status")


# class AccNotesEmails(dataobj.DataObj, AccNotesEmailsDAO):
class AccNotesEmails(AccNotesEmailsDAO):
    """
    Class for notes/emails/to-dos associated with accounts
    """
    def _keep_fields(self, keep_keys):
        for key in list(self.data.keys()):
            if key not in keep_keys:
                del self.data[key]

    def _insert_rec(self, rec_type, keep_keys):
        self._keep_fields(keep_keys)
        self.data["type"] = rec_type
        self.data["bulk_email_id"] = None   # Only used by Bulk email
        return self.insert()

    def insert_email(self):
        return self._insert_rec("E",
                                # ("acc_id", "to_addr", "cc_addr", "subject", "body", "err_tbl", "err_ids", "status")
                                ("acc_id", "to_addr", "cc_addr", "subject", "body", "err_ids", "status")
                                )

    def insert_note(self):
        return self._insert_rec("N", ("acc_id", "subject", "body", "status"))

    def insert_todo(self):
        return self._insert_rec("T", ("acc_id", "subject", "body", "status"))

    @classmethod
    def list_notes_emails_todos_dicts(cls, acc_id, limit=None, rec_type=None, status=None):
        """
        Retrieve notes &/or ToTos &/or email messages related to particular accounts, & which have specified
        status (None, Highlighted, Resolved, Deleted).
        These items are returned from `acc_notes_emails` and, for bulk-emails, the `acc_bulk_email` table via
        a single bespoke SQL query involvig`acc_notes_email LEFT JOIN acc_bulk_email` that retrieves
        `subject` & `body` fields from acc_bulk_email where they exist.

        :param acc_id: Number - Account ID
        :param limit: Number - Maximum number of records to retrieve; or empty string or None if ALL recs reqd
        :param rec_type: None or String - Types of record to return:
                            "N" (Note), "E" (Email), "T" (ToDo), "NET" (Notes & Emails).
        :param status: None or String - Single status or concatenated string of statuses of records to return:
                            "N" (Null status), "H" (Highlighted), "R" (Resolved),  "D" (Deleted) or any combination
                            (e.g. "HNR").

        :return: List of record dicts
        """
        def recreate_dict_bspk(rec_tuple):
            """
            :param rec_tuple: Tuple containing `acc_notes_emails` record fields PLUS the subject & body from
                              `acc_bulk_email` record (which may be NULL --> None)
            """
            # Recreate the acc_notes_emails record from the base data (all except last 2 fields in rec_tuple)
            rec_dict = cls.recreate_json_dict_from_rec(rec_tuple[:-2])
            # If Bulk email subject & body are present, then use those (both will either be None or have a string value)
            bulk_subj = rec_tuple[-2]
            if bulk_subj is not None:
                rec_dict["subject"] = bulk_subj
                rec_dict["body"] = rec_tuple[-1]
            return rec_dict

        limit = int(limit) if limit else None
        if not rec_type:
            rec_type = "NETB"  # Notes & Emails & ToDos & Bulk Emails
        if not status:
            status = "HNR"   # Not deleted
        return [recreate_dict_bspk(rec_tuple) for rec_tuple in cls.bespoke_pull(acc_id, status, rec_type,
                                pull_name="bspk_notes_emails_status_for_ac", limit_offset=limit)]

    @classmethod
    def update_status(cls, rec_id=None, status=None):
        """
        Update status indicator for specified rec ID.

        :param rec_id: Id of record to update
        :param status: String - "R" (Resolved), "H" (Highlight), "D" (Delete), "" (Remove highlight)

        :return: Integer - Number of records affected
        """
        if status in ("", "N"):
            status = None   # causes NULL to be set in database
        return cls.bespoke_update(status, rec_id, query_name="update_status")

    @classmethod
    def update_status_bulk_emails(cls, bulk_id=None, status=None):
        """
        Update status indicator for emails with bulk_email_id matching that provided.

        :param bulk_id: bulk_email_id of records to update
        :param status: String - "R" (Resolved), "H" (Highlight), "D" (Delete), "" (Remove highlight)

        :return: Integer - Number of records affected
        """
        if status in ("", "N"):
            status = None   # causes NULL to be set in database
        return cls.bespoke_update(status, bulk_id, query_name="update_status_bulk_id")

    @classmethod
    def update_note_email_status(cls, note_or_email_ids=None, status=None):
        """
        Update status indicator for specified IDs. May update multiple records in acc_notes_emails table.

        :param note_or_email_ids: List of number - Ids of records to update
        :param status: String - "R" (Resolved), "H" (Highlight), "D" (Delete), "" (Remove highlight)

        :return: Integer - Number of records affected
        """
        cls.start_transaction()
        updated_count = 0
        if status == "":
            status = None   # causes NULL to be set in database
        for id in note_or_email_ids:
            updated_count += cls.bespoke_update(status, id, query_name="update_status", commit=False)
        cls.commit()
        return updated_count


class AccRepoMatchParams(dataobj.DataObj, AccRepoMatchParamsDAO):
    """
    Class for Matching Parameters associated with Repository accounts

    Data model:
        {
            "id": <(parent) Account ID>,
            "created": <date record created>,
            "updated": <date record created>,
            "has_regex": <Boolean - True: Regex is currently used; False (or None): No regex>,
            "had_regex": <Boolean - True: Regex previously used; False (or None): No regex ever used>,
            "orig_name_variants": <"List of Original name_variants - populated IF regex is used">,
            "matching_config": {
                "name_variants": ["<list of name variants (University of Jisc, Jisc University, etc..) associated with this institution><list of strings>"],
                "orcids": ["<list of author ORCIDS><list of strings>]"
                "emails": ["<list of author emails><list of strings>]"
                "domains": ["<list of the web/email domains associated with this institution><list of strings>]",
                "grants": ["<list of grant numbers associated with this institution><list of strings>]",
                "postcodes": ["<list of postcodes of property affiliated with this institution><list of strings>]"
                "org_ids": [ "<list of Organisation identifiers of form: 'TYPE: value'><list of strings>"]
            },
        }

    """
    @property
    def matching_config(self):
        # Gets the matching config data. If None, both sets and returns an empty dictionary instead
        val = self._get_single("matching_config")
        if not val:
            val = {}
            self._set_single("matching_config", val)
        return val

    @matching_config.setter
    def matching_config(self, val):
        self._set_single("matching_config", val)


    @property
    def domains(self):
        return self._get_list("matching_config.domains")

    @domains.setter
    def domains(self, val):
        self._set_list("matching_config.domains", val)

    @property
    def name_variants(self):
        return self._get_list("matching_config.name_variants")

    @name_variants.setter
    def name_variants(self, val):
        self._set_list("matching_config.name_variants", val)

    @property
    def author_emails(self):
        return self._get_list("matching_config.emails")

    @author_emails.setter
    def author_emails(self, val):
        self._set_list("matching_config.emails", val)

    @property
    def author_orcids(self):
        return self._get_list("matching_config.orcids")

    @author_orcids.setter
    def author_orcids(self, val):
        self._set_list("matching_config.orcids", val)

    @property
    def postcodes(self):
        return self._get_list("matching_config.postcodes")

    @postcodes.setter
    def postcodes(self, val):
        self._set_list("matching_config.postcodes", val)

    @property
    def grants(self):
        return self._get_list("matching_config.grants")

    @grants.setter
    def grants(self, val):
        self._set_list("matching_config.grants", val)

    @property
    def org_ids(self):
        return self._get_list("matching_config.org_ids")

    @org_ids.setter
    def org_ids(self, val):
        self._set_list("matching_config.org_ids", val)

    @property
    def formatted_org_ids(self):
        """
        Return organisation IDs with a space following the colon
        """
        return [oid.replace(":", ": ") for oid in self._get_list("matching_config.org_ids")]

    @property
    def last_updated(self):
        # return config last updated time in "YYYY-mm-ddT%HH:MM:SSZ" format
        return self._get_single("updated")

    def last_updated_formatted(self, fmt="%d/%m/%Y %H:%M:%S"):
        # return config last updated timestamp string format
        last_updated = self.last_updated
        return dates.reformat(last_updated, out_format=fmt) if last_updated else ""

    @property
    def has_regex(self):
        return self._get_single("has_regex")

    @has_regex.setter
    def has_regex(self, val):
        self._set_single("has_regex", val)

    @property
    def had_regex(self):
        return self._get_single("had_regex")

    @had_regex.setter
    def had_regex(self, val):
        self._set_single("had_regex", val)

    @property
    def orig_name_variants(self):
        return self._get_list("orig_name_variants")

    @orig_name_variants.setter
    def orig_name_variants(self, val):
        self._set_list("orig_name_variants", val)

    def set_has_regex(self):
        """
        Check if name_variants have regex & if so, set the has_regex flag.

        :return: Boolean - indicates if regex found
        """
        for name_var in self.name_variants:
            if includes_regex.search(name_var):
                self.has_regex = True
                return True     # Exit loop & return
        self.has_regex = False
        return False

    @classmethod
    def _remove_redundant_matching_params_and_sort(cls, config_dict):
        """
        Remove duplicate and redundant matching params.  Sort the following: grants, postcodes, orcids, emails, org_ids.
        Return list of redundant messages.

        We consider a name variant A redundant if there exists a name variant B which is a substring of A (B < A).
        This is because if we discover an affiliation C for which A is a substring of C (A < C), then B will also
        be a substring of C as B < A < C. Therefore the name variant A is rendered redundant by B. For example if
        we have name variant "Ben" and name variant "Ben Murray" and we find an affiliation "Ben Murray is great"
        then the name variant "Ben" will already catch the affiliation and "Ben Murray" becomes redundant (but still
        great)

        We consider a domain redundant if there exists another domain which the domain ends with. For example
        pubrouter.jisc.ac.uk is rendered redundant by jisc.ac.uk, but not by pubrouter.jisc.ac (or something like that)

        We consider an email address redundant if it will already be caught by a domain listed in domains. For example
        if we have a domain listed "jisc.ac.uk" and an author email of "jisc-dev@jisc.ac.uk" then the email would be
        caught by the domain regardless of having the email listed.

        Additionally, removes any duplicates found in any of the matching params. These removals are NOT reported in the
        returned list of messages.

        :param config_dict: Dict of Matching parameters {key-word: [param-list], ...} - *** MAY BE UPDATED ***
        :return: A list of messages detailing removals and why they've occurred
        """
        def _log_message(msg):
            # little helper function which logs and appends a redundancy message to our list
            redundant_messages.append(msg)
            current_app.logger.info(msg)
            return True

        # deal with redundant name variants
        # use list to keep a hard copy so we don't miss elements in our for loop
        redundant_messages = []

        name_vars = config_dict.get("name_variants")
        if name_vars is not None:
            final_name_vars = []
            # sort names by string length (shortest first)
            name_vars = sorted(list(name_vars), key=len)
            while name_vars:
                # pop the last element in the list (longest name)
                longer_name = name_vars.pop()
                redundancy_found = False
                for variant in name_vars:
                    # See if first variant is a substring of variant
                    if variant in longer_name:
                        redundancy_found = _log_message(
                            f"Name Variant: '{longer_name}' removed, as made redundant by '{variant}'")
                        break
                if not redundancy_found:
                    final_name_vars.append(longer_name)
            final_name_vars.reverse()         # Order shortest to longest
            config_dict["name_variants"] = final_name_vars

        # deal with redundant domains
        domains = config_dict.get("domains")
        if domains is not None:
            # sort domains by string length (shortest first)
            domains = sorted(list(set(domains)), key=len)
            final_domains = []
            while domains:
                longer_domain = domains.pop()
                redundancy_found = False
                for domain in domains:
                    if longer_domain.endswith(f".{domain}"):
                        redundancy_found = _log_message(
                            f"Domain: '{longer_domain}' removed, as made redundant by '{domain}'")
                        break
                if not redundancy_found:
                    final_domains.append(longer_domain)
            final_domains.reverse()     # Order shortest to longest
            config_dict["domains"] = final_domains

        # deal with duplicates in postcodes, grants, ORCiDs and OrgIds by converting to a set then back to a list
        for config_key in ("grants", "postcodes", "orcids", "org_ids"):
            config_list = config_dict.get(config_key)
            if config_list is not None:
                config_dict[config_key] = sorted(list(set(config_list)))

        emails = config_dict.get("emails")
        if emails is not None:
            domains_list = config_dict.get("domains", [])
            emails = list(set(emails))  # Remove any duplicates
            # deal with redundant author emails
            # use a copy so no issues when removing items from the master emails list
            for email in emails.copy():
                # if our email has the same domain as any of our domains, remove it
                for domain in domains_list:
                    if email.endswith(domain):
                        _log_message(f"Author Email: '{email}' removed, as matches domain '{domain}'")
                        emails.remove(email)
                        break
            config_dict["emails"] = sorted(emails)

        return redundant_messages

    def remove_redundant_matching_params_and_sort(self):
        return self._remove_redundant_matching_params_and_sort(self.matching_config)

    @classmethod
    def update_match_params(cls, acc_id, org_name, acc_uuid, csvfile=None, jsoncontent=None, add=False):
        """
        Store Repository Account matching parameters - either uploaded from CSV file or submitted as JSON object

        Matching param fields are 'Domains','Name Variants','Author Emails','Postcodes','Grant Numbers','ORCIDs'

        New parameters either REPLACE existing params (default behaviour) or are ADDED to existing.
        :param acc_id: Account ID
        :param org_name: Account Organisation-name
        :param acc_uuid: Account UUID
        :param csvfile: Stream of CSV file containing matching params
        :param jsoncontent: Dict of matching params (from JSON format)
        :param add: Boolean - True: new matching params are ADDED to existing; False: new match params REPLACE existing

        :return Tuple: (None, None, None) OR
                (List-of-matching-param-types-loaded, list-of-redundancies-removed, AccRepoMatchParams object).
        """
        bad_data_errors = []

        def strip_remove_multispace(s):
            """
            Helper function - strips text of leading & trailing spaces, and replaces multiple spaces by single space.
            :param s: String data
            :return: stripped text
            """
            # Strip white space from start/end of s, then replace any multiple white-space by a single space
            return match_multispace_regex.sub(" ", s.strip())

        def strip_domain(value):
            """
            Helper function to:
                - remove any leading 'http(s)://' string
                - remove any trailing '/'
                - convert result to lower case
            :param value: String data
            :return: stripped text
            """
            value = value.strip().lower()
            # If string starts with http, then remove the http:// or https://
            if value.startswith("http"):
                # Assume string starts with one of these: http:// or https:// so search for '//' starting after the http
                offset = value[4:].find("//")
                if offset != -1:
                    # substring from after the '//'
                    value = value[6 + offset:]

            # Extract domain (if supplied in form: some.domain.com/extension or some.domain.com/)
            return value.split('/', maxsplit=1)[0]  # take first element of resulting array

        def strip(val):
            """
            Strip spaces at beginning & end of string
            :param val: String
            :return: string
            """
            return val.strip()

        def strip_lower(val):
            """
            Strip spaces at beginning & end of string, convert to lower case
            :param val: String
            :return: string
            """
            return val.strip().lower()

        def parse_org_id(orig_value):
            """
            Organisation ID of types GRID, ROR, ISNI or Crossref (Fundref) can be presented in one of 2 forms:
                * "TYPE:ID-value" e.g. "ROR:0524sp257" or "ISNI:0000000419367603" / "ISN:0000000419367603" or
                                        "CROSSREF:501100000883", "GRID:grid.1111.2"
                * "Identfier URL" e.g. "https://ror.org/0524sp257", "https://isni.org/isni/0000000419367603",
                                        "https://api.crossref.org/funders/501100000883"
            :return: None or Id value of form: "TYPE:ID-value"}
            """
            id_parts = None
            value = orig_value.strip().lower()
            # If string starts with http, then remove the http:// or https://
            if value.startswith("http"):
                # Assume string starts with one of these: http:// or https:// so search for '//' starting after the http
                offset = value[4:].find("//")
                if offset != -1:
                    # substring from after the '//'
                    value = value[6 + offset:]
                    id_parts = value.split("/")
                    # If URL ended with a "/", then remove the empty segment string
                    if id_parts[-1] == "":
                        id_parts.pop()
            else:   # Assume we have "type:id-value" or "type: id-value" string
                id_parts = split_org_id_regex.split(value)
                if len(id_parts) == 2:
                    # We need to remove any spaces from ID Value (e.g. ISNI can be "1111 2222 3333 4444")
                    if " " in id_parts[1]:
                        id_parts[1] = id_parts[1].replace(" ", "")
                else:   # Unexpected string format
                    id_parts = None

            if not id_parts:
                bad_data_errors.append(
                    f"Organisation ID '{orig_value}' has bad format - expect a valid URL or 'TYPE: id-value' string")
                # raise Exception(
                #     f"Organisation ID '{orig_value}' has bad format - expect a valid URL or 'TYPE: id-value' string")
                return None

            # List of tuples: [("key-word-to-match", "TYPE-value"), ...]
            possible_identifiers = [("ror", "ROR"), ("isn", "ISNI"), ("grid", "GRID"), ("crossref", "CROSSREF"), ("rin", "RINGGOLD")]
            # Look for identifier keyword, if found return formatted id string
            for keyword, id_type in possible_identifiers:
                if keyword in id_parts[0]:
                    return f"{id_type}:{id_parts[-1]}"

            # raise Exception(f"Organisation ID '{orig_value}' is NOT one of acceptable types - ROR, ISNI or Crossref")
            bad_data_errors.append(f"Organisation ID '{orig_value}' is NOT one of acceptable types - GRID, ROR, ISNI, Ringgold or Crossref")
            return None

        def load_from_csv(csvfile, matching_config):
            """
            :return: Tuple - (String- content type, Dict- Matching params)
            """
            # Make sure csvfile is valid UTF-8 - otherwise fail
            csvfile = bytes_io_to_string_io(csvfile)
            # Dictionary that maps column heading keywords to a tuple containing matching params data model key,
            # and a method to convert the data into the correct format.
            # NOTE: during processing, entries are popped from this dict as tuples are added to column_mapping list
            param_key_map = {
                # "column-key-word": ("match-params-data-model-key", conversion-func)
                "variants": ('name_variants', strip_remove_multispace),
                "domain": ('domains', strip_domain),
                "postcode": ('postcodes', strip_remove_multispace),
                "grant": ('grants', strip_remove_multispace),
                "orcid": ('orcids', strip),
                "email": ('emails', strip_lower),
                "identifier": ('org_ids', parse_org_id)
            }

            # List of tuples (data model key, transformation function) selected from param_key_map
            # ordered by CSV file column heading
            # E.g. if first CSV file column is "Orcid info",
            # the first element will contain: ('orcids', strip)
            column_mapping = []

            read_csv = csv_reader(csvfile)

            ## Process CSV column headings row ##

            # Assume that first row of CSV file contains Column Headings
            # Identify the columns that are relevant to us, by checking column heading text against param_key_map
            for col_heading in next(read_csv, []):
                # If param_key_map is empty, we have all the columns we need - the rest are garbage
                if not param_key_map:
                    break
                col_heading = strip_lower(col_heading)  # Strip leading/trailing spaces and convert to lowercase
                # col_heading is an empty string
                if "" == col_heading:
                    # We are going to ignore columns with empty heading value
                    key_func_tuple = (None, None)
                else:
                    key_func_tuple = None
                    # See if the column heading contains a column keyword (from param_key_map)
                    # Iterate over the param_key_map and attempt to match the column heading to a field
                    for key_word in param_key_map:
                        # If the parameter key appears in any part of this column heading
                        # (e.g. if "email" appears in "author emails" heading)
                        if key_word in col_heading:
                            # store the tuple of the matched map entry and remove it (pop) from the map dictionary
                            key_func_tuple = param_key_map.pop(key_word)
                            # Initialise matching_config dict for this column
                            matching_config[key_func_tuple[0]] = []
                            break
                    # if the column heading was garbage (and has a value- note many CSVs accidentally get headers added
                    # to them when converting from xslx to csv)
                    if key_func_tuple is None:
                        raise Exception(
                            f"Matching parameters CSV file contained an unrecognized column header: '{col_heading}'")

                column_mapping.append(key_func_tuple)

            ## Process remainder of CSV file ##

            # Loop through each row of CSV data
            for row in read_csv:
                for index, item in enumerate(row):
                    try:
                        key, transform_func = column_mapping[index]
                    except IndexError:
                        # If we have more columns then we have expected columns, just continue to the next row.
                        break
                    if key and item:
                        config_value = transform_func(item)
                        if config_value:
                            matching_config[key].append(config_value)

            return "CSV", matching_config

        def load_from_json(jsoncontent, matching_config):
            """
            :return: Tuple - (String- content type, Dict- Matching params)
            """
            # Dictionary that maps matching param keys to a method to convert the data into the correct format.
            # save the lines into the repo config
            param_key_map = {
                'name_variants': strip_remove_multispace,
                'domains': strip_domain,
                'postcodes': strip_remove_multispace,
                'grants': strip_remove_multispace,
                'orcids': strip,
                'emails': strip_lower,
                'org_ids': parse_org_id
            }
            for k in jsoncontent:
                # Check that key is valid
                if k in param_key_map:
                    # Check that we have a list
                    if isinstance(jsoncontent[k], list):
                        # Get the transformation/normalisation method for this type of matching param
                        transform_func = param_key_map[k]
                        # normalise/check each element in the array
                        matching_config[k] = [transform_func(x) for x in jsoncontent[k]]

            return "JSON", matching_config

        ### FUNCTION BODY ###
        matching_config = {}
        if csvfile is not None:
            content_type, matching_config = load_from_csv(csvfile, matching_config)
        elif jsoncontent is not None:
            content_type, matching_config = load_from_json(jsoncontent, matching_config)
        # no JSON or csv submitted
        else:
            current_app.logger.error(f"No valid matching config file submitted for repo account id: {acc_id} ({org_name})")
            return None, None, None

        if bad_data_errors:
            raise Exception("; ".join(bad_data_errors))

        # No matching config loaded
        if not matching_config:
            return [], None, None

        ## If we get this far then we have new matching config loaded ##

        # Retrieve current matching params object
        curr_match_params_obj = cls.pull(acc_id, for_update=True)
        archived_data = None
        # New record
        if curr_match_params_obj is None:
            # Deduplicate & sort matching config
            redundancies = cls._remove_redundant_matching_params_and_sort(matching_config)
            curr_match_params_obj = cls({
                "id": acc_id,
                "created": None,
                "updated": None,
                "has_regex": None,
                "orig_name_variants": None,
                "matching_config": matching_config
            })
            had_regex = False
            uses_regex = curr_match_params_obj.set_has_regex()
            curr_match_params_obj.insert()
        else:   # Existing record
            had_regex = curr_match_params_obj.has_regex
            # Create copy current params which will be saved in archive table if saving new set is successful
            params_to_archive_dict = deepcopy(curr_match_params_obj.data)

            curr_config_dict = curr_match_params_obj.matching_config
            # Update current matching_config with new values
            for key, vals_list in matching_config.items():
                if add:
                    try:
                        # New values are added to existing
                        curr_config_dict[key].extend(vals_list)
                    except KeyError:
                        # existing config didn't yet have the key
                        curr_config_dict[key] = vals_list
                else:
                    # new values replace existing
                    curr_config_dict[key] = vals_list

            # Deduplicate & sort matching config
            redundancies = cls._remove_redundant_matching_params_and_sort(curr_config_dict)
            curr_match_params_obj.matching_config = curr_config_dict
            uses_regex = curr_match_params_obj.set_has_regex()
            if had_regex:
                curr_match_params_obj.had_regex = True
            elif uses_regex:
                # If this is first time that regex has been found, then store non-regex version of name_variants
                curr_match_params_obj.orig_name_variants = params_to_archive_dict.get("matching_config", {}).get("name_variants", [])
            curr_match_params_obj.update()

            archived_data = AccRepoMatchParamsArchived.create_archive_rec(params_to_archive_dict)

        view_url = url_for('account.view_match_params', repo_uuid=acc_uuid, _external=True)
        # Log a Warning if previously had regex, but now no longer do
        log_level = INFO
        regex_note = ""
        subj_note = ""
        if uses_regex:
            regex_note = " - HAS REGEX"
        elif had_regex:
            log_level = WARNING
            regex_note = " - IMPORTANT: Name variants NO LONGER INCLUDE REGEX"
            subj_note = " - RegEx removed!"

        updated_saved = 'updated' if add else 'saved'
        current_app.logger.log(
            log_level,
            f"Matching parameters {list(matching_config.keys())} {updated_saved} for Repo account ID: {acc_id} ({org_name}){regex_note} - {view_url}." + (f"\n Previous matching params archived with PKID: {archived_data['pkid']}." if archived_data else ""),
            extra={"mail_it": True, "subject": f"Matching params {updated_saved}{subj_note}"})

        return matching_config.keys(), redundancies, curr_match_params_obj


    @classmethod
    def get_summary_info(cls, min_status=0):
        """
        Obtain list of account Org-Names, IDs, UUIDs, Status, Updated, Has-regex, Count-archived params
        :param min_status: Integer - Minimum account status (0 -> All account (ON & OFF), 1 -> Accounts turned ON)
        :return: List of account org-name, id, UUID, Status, Updated, has-regex, count-archived
        """
        return cls.bespoke_pull(min_status, pull_name="bspk_summary")


class AccRepoMatchParamsArchived(dataobj.DataObj, AccRepoMatchParamsArchivedDAO):
    """
    Class for Archived Matching Parameters associated with Repository accounts

    Data model:
        {
            "pkid": <Unique ID>,
            "archived": <date record created>,
            "id": <(parent) Account ID>,
            "updated": <date record created>,
            "has_regex": <Boolean - True: Regex is used; False (or None): No regex>,
            "matching_config": {
                "name_variants": ["<list of name variants (University of Jisc, Jisc University, etc..) associated with this institution><list of strings>"],
                "orcids": ["<list of author ORCIDS><list of strings>]"
                "emails": ["<list of author emails><list of strings>]"
                "domains": ["<list of the web/email domains associated with this institution><list of strings>]",
                "grants": ["<list of grant numbers associated with this institution><list of strings>]",
                "postcodes": ["<list of postcodes of property affiliated with this institution><list of strings>]"
                "org_ids": [ "<list of Organisation identifiers of form: 'TYPE: value'><list of strings>"]
            },
        }

    """
    @property
    def pkid(self):
        return self._get_single("pkid")

    @property
    def archived(self):
        return self._get_single("archived")

    def archived_datetime_str(self, fmt="%d/%m/%Y %H:%M:%S"):
        return self.archived.strftime(fmt)

    @property
    def matching_config(self):
        # Gets the matching config data. If None, both sets and returns an empty dictionary instead
        val = self._get_single("matching_config")
        if not val:
            val = {}
            self._set_single("matching_config", val)
        return val

    @property
    def domains(self):
        return self._get_list("matching_config.domains")

    @property
    def name_variants(self):
        return self._get_list("matching_config.name_variants")

    @property
    def author_emails(self):
        return self._get_list("matching_config.emails")

    @property
    def author_orcids(self):
        return self._get_list("matching_config.orcids")

    @property
    def postcodes(self):
        return self._get_list("matching_config.postcodes")

    @property
    def grants(self):
        return self._get_list("matching_config.grants")

    @property
    def org_ids(self):
        return self._get_list("matching_config.org_ids")

    @property
    def formatted_org_ids(self):
        """
        Return organisation IDs with a space following the colon
        """
        return [oid.replace(":", ": ") for oid in self._get_list("matching_config.org_ids")]

    @property
    def last_updated(self):
        # return config last updated time in "YYYY-mm-ddT%HH:MM:SSZ" format
        return self._get_single("updated")

    def last_updated_formatted(self, fmt="%d/%m/%Y %H:%M:%S"):
        # return config last updated timestamp string format
        last_updated = self.last_updated
        return dates.reformat(last_updated, out_format=fmt) if last_updated else ""

    @property
    def has_regex(self):
        return self._get_single("has_regex")

    @has_regex.setter
    def has_regex(self, val):
        self._set_single("has_regex", val)

    @classmethod
    def list_archived_match_param_pkids_for_org(cls, org_id):
        return cls.bespoke_pull(org_id, pull_name="bspk_all_4_acc")

    @classmethod
    def count_archived_match_param_pkids_for_org(cls, org_id):
        return cls.count(org_id, pull_name="all_4_acc")

    @classmethod
    def create_archive_rec(cls, match_params_dict):
        """
        Create an archive record from original match_params_dict
        :param match_params_dict: Original match params
        :return: Dict - archived data
        """
        # Remove fields NOT required in archive record
        for k in ("created", "orig_name_variants", "had_regex"):
            match_params_dict.pop(k, None)
        # Save original match-params data in archive
        return AccRepoMatchParamsArchivedDAO(match_params_dict).insert()

    def revert_to_these_params(self):
        """
        Update the corresponding AccRepoMatchParams record with current archived values.  Save the current record as
        an archived record.
        :return:  New archive Object
        """
        # Retrieve current matching params to be replaced
        match_params = AccRepoMatchParams.pull(self.id, for_update=True)
        orig_params_dict = deepcopy(match_params.data)

        # Set matching params to archive values
        match_params.matching_config = self.matching_config
        match_params.has_regex = self.has_regex
        match_params.update()

        return AccRepoMatchParamsArchived(self.create_archive_rec(orig_params_dict))
