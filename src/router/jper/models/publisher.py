"""
Models that only apply to publishers
"""
from datetime import datetime
from dateutil.relativedelta import relativedelta
from octopus.lib import dataobj
from router.shared.mysql_dao import PubTestRecordDAO, PubDepositRecordDAO, ReportingHelperMixin

# scroll_num values: help ensure that Scrollers use unique connections (though uniqueness is conferred by scroll_name
# which is a composite of scroll_num, pull_name and other attributes).
# IMPORTANT check entire code base for other similar declarations before adding new ones (or changing these numbers) to
# avoid overlaps - do global search for "_SCROLL_NUM ="
PUB_DEPOSIT_SCROLL_NUM = 10


class PublisherDepositRecord(dataobj.DataObj, PubDepositRecordDAO, ReportingHelperMixin):
    __type__ = None

    def __init__(self, raw=None):
        """
        Model for a PublisherDepositRecord - stores data about publisher deposits (API deposits, FTP, SWORD, etc...)

        Field definitions:
        { 
            "id": "<ID of this pub_deposit_record>",
            "pub_id": "<Publisher id of depositor>",
            "note_id": "<Corresponding notification_id to this record>",
            "created": "<Date this record was created>",
            "updated": "<Date this record was last updated>",
            "name": "<Name of file deposited in tmparchive>",
            "matched": "<Whether the corresponding notification was matched to any repo>",
            "matched_live": "<Whether the corresponding notification was matched to a LIVE repo>"
            "successful": "<Whether the submission was correctly processed>",
            "error": "<Error message if a failure occurs during processing>",
            "type": "<Type of deposit: 'F' (FTP), 'A' (API) or 'S' (Sword) depending on type of deposit>",
            "sword_in_progress": "<bool used during sword-in deposits to store whether a sword deposit is in progress>",
            "err_emailed": "<Boolean indicates whether error has been included in an email sent to account contact>"
        }
        :param raw: raw data, a dictionary in a format like the one above. MUST have keys valid to the struct
            definition.
        """
        struct = {
             "fields": {
                "id": {"coerce": "integer"},
                "note_id": {"coerce": "integer"},
                "pub_id": {"coerce": "integer"},
                "created": {"coerce": "utcdatetime"},
                "updated": {"coerce": "utcdatetime"},
                "name": {},
                "matched": {"coerce": "bool"},
                "matched_live": {"coerce": "bool"},
                "successful": {"coerce": "bool"},
                "error": {},
                "type": {"allowed_values": ["S", "F", "A"]},    # Indicates: Sword / FTP / API
                "sword_in_progress": {"coerce": "bool"},
                "err_emailed": {"coerce": "bool"},
                },
            }
        self._add_struct(struct)
        super().__init__(raw=raw)
        if self.data.get("type") is None:
            self.data["type"] = self.__type__

    @property
    def type(self):
        return self._get_single("type")

    @type.setter
    def type(self, value):
        self._set_single("type", value)

    @property
    def error(self):
        return self._get_single("error")

    @error.setter
    def error(self, value):
        self._set_single("error", value)

    @property
    def publisher_id(self):
        return self._get_single("pub_id")

    @publisher_id.setter
    def publisher_id(self, value):
        self._set_single("pub_id", value)

    @property
    def notification_id(self):
        return self._get_single("note_id")

    @notification_id.setter
    def notification_id(self, value):
        self._set_single("note_id", value)

    @property
    def name(self):
        return self._get_single("name")

    @name.setter
    def name(self, value):
        self._set_single("name", value)

    @property
    def matched(self):
        return self._get_single("matched", coerce=dataobj.to_bool)

    @matched.setter
    def matched(self, value):
        self._set_single("matched", value, coerce=dataobj.to_bool)

    @property
    def matched_live(self):
        return self._get_single("matched_live", coerce=dataobj.to_bool)

    @matched_live.setter
    def matched_live(self, value):
        self._set_single("matched_live", value, coerce=dataobj.to_bool)

    @property
    def successful(self):
        return self._get_single("successful", coerce=dataobj.to_bool)

    @successful.setter
    def successful(self, value):
        self._set_single("successful", value, coerce=dataobj.to_bool)

    @classmethod
    def get_all(cls):
        """
        Retrieves all records of a given type

         :return: A list of ftp records of given type
        """
        return cls.pull_all(cls.__type__, pull_name="all_by_type")

    @classmethod
    def get_all_from_publisher(cls, pub_id, limit_offset=None):
        """
        Retrieves all records from a given publisher

        :param pub_id: Publisher's account ID
        :param limit_offset: Integer - number of recs or List [page-size, offset-of-first-rec] [OPTIONAL]

        :return: A list of ftp records for a given publisher
        """
        return cls.pull_all(pub_id, pull_name="all_4_pub", limit_offset=limit_offset)

    @classmethod
    def days_since_last_deposit(cls, pub_id):
        """
        Returns the number of days since a publisher last made a deposit
        
        :param pub_id: Publisher's account id
        
        :return: an integer 
        """
        # get the first item returned by the query (the most recent one)
        obj_list = cls.pull_all(pub_id, pull_name="all_4_pub", limit_offset=1)

        if obj_list:
            newest_date = obj_list[0].created
            if newest_date:
                # calculate number of days since last deposit (no need to force to timezone aware)
                return (datetime.now() - datetime.strptime(newest_date, "%Y-%m-%dT%H:%M:%SZ")).days
        return None

    @classmethod
    def get_by_notification_id(cls, note_id, for_update=False):
        """
        Get a pub_deposit_record matching a given notification id

        :param note_id: Notification ID to search for
        :param for_update: Boolean - indicates whether we expect to perform an update

        :return: FTP record corresponding to the given note_id, or None.
        """
        return cls.pull(note_id, pull_name="note_id", for_update=for_update)

    @classmethod
    def aggregate_pub_deposit_daily(cls,
                                    publisher_id,
                                    from_date=None,
                                    to_date=None,
                                    page=None,
                                    page_size=None,
                                    do_count=True,
                                    rec_format=None,
                                    col_headings=None,
                                    ):
        """
        Retrieve report of publisher submissions between 2 dates, with results returned as a list of tuples.

        Each tuple contains:
          (Date, Type:f/a/s, Submission-count, Count-successful, Count-matched, Count-matched-live, Names-of-files*, Errors*)
        NOTE: the Names-of-files and Errors are Strings of text separated by '|' character - they can be split into lists
        :param publisher_id: Id of the publisher
        :param to_date: String to-date ("YYYY-MM-DD")
        :param from_date: String from-date ("YYYY-MM-DD")
        :param page: page number in result set to return
        :param page_size: number of results to return in this page of results
        :param do_count: Boolean - True: Calculate total count; False: Don't necessarily calculate total
        :param rec_format: Integer (dao.RAW, dao.DICT, dao.WRAP) or a reference to a formatting function
        :param col_headings: List of Strings - column headings OR None
        :return: Tuple - (Count-of-total-recs, DAOScroller object for iterating over records. column-headings-list or None)
        """
        count, scroller = cls.aggregate_over_time_period(
            publisher_id, pull_name="bspk_daily_stats", to_date=to_date, from_date=from_date, page=page,
            page_size=page_size, do_count=do_count, rec_format=rec_format, scroll_num=PUB_DEPOSIT_SCROLL_NUM)
        return count, scroller, col_headings

    @classmethod
    def recs_scroller_for_csv_file(cls, publisher_id, from_date=None, to_date=None, page=None, page_size=None):
        """
        Simple method to convert a list of record tuples to a csv-writable list of tuples for use on the deposit history
        page of a publisher. Each tuple will store deposit date, number of deposits, number successful, number matched,
        error details, whether deposit made by FTP or API).

        :param publisher_id: ID of the publisher we want to get statistics about
        :param from_date: String "YYYY-MM-DD" - Earliest date to generate statistics for. If not supplied, will take
            everything until the to_date (so, anything that is before the to_date.)
        :param to_date: String "YYYY-MM-DD" - Latest date we want to have statistics for. Will default to today.
        :param page: page number in result set to return
        :param page_size: number of results to return in this page of results

        :return: Tuple - (Count-of-total-recs, DAOScroller object for iterating over records. column-headings-list)
        """
        def format_rec(rec_tuple):
            # Each tuple contains:
            #   (Date, Type:f/a/s, Submission-count, Count-successful, Count-matched, Count-matched-live, Names-of-files*, Errors*)
            # NOTE: the Names-of-files and Errors are Strings of text separated by '|' character - they can be split into lists

            # Take [0]Date, [1]Type, [2]Total, [3]Successful, [4]Matched from rec_tuple
            row = list(rec_tuple[0:5])
            row[1] = {"A": "api", "F": "ftp", "S": "sword"}.get(row[1], "")  # Replace single character code by description
            row.append(ReportingHelperMixin.reformat_array_string(rec_tuple[6]))    # Error files
            row.append(ReportingHelperMixin.reformat_array_string(rec_tuple[7]))    # Error messages
            return row

        return cls.aggregate_pub_deposit_daily(
            publisher_id, from_date, to_date, page, page_size, do_count=False, rec_format=format_rec,
            col_headings=["Date", "Type", "Total", "Successful", "Matched", "Error Files", "Error Messages"]
        )

    @classmethod
    def get_formatted_errors_for_id_list(cls, pub_deposit_ids):
        """
        Return list of dates & formatted error tuples for given ids [(date, formatted-error), ...]
        """
        # bespoke_pull returns list of tuples - we expect a single element list with a 2 element tuple
        # (date, formatted-error) for each Id
        # No need to use a scroller here as expect relatively few, small records to be retrieved
        return [cls.bespoke_pull(id_, pull_name="bspk_errmsg_by_id")[0] for id_ in pub_deposit_ids]

    @classmethod
    def update_to_indicate_errors_emailed(cls, pub_deposit_ids):
        """
        Update records to show that error included in email
        """
        for id_ in pub_deposit_ids:
            cls.bespoke_update(id_, query_name="update_err_emailed_true")

    @classmethod
    def duplicate_doi_query(cls, from_date=None, to_date=None, days_margin=0):
        """
        Bespoke query to retrieve duplicate DOI information.
        The DB query will gather data from (from_date - days_margin) to (to_date + days_margin) to attempt to capture
        all duplicates that may occur around the time of from_date & to_date.  The returned records are then checked to
        see if any duplicates occurred during actual from_date & to_date, and if so they are included within returned
        dataset, any records without a deposit_date within from_date - to_date range are discarded.
        :param from_date: String "YYYY-MM-DD" - Earliest date to produce report for. If not supplied, will default to
                1 month before to_date.
        :param to_date: String "YYYY-MM-DD" - Latest date to produce report for. Will default to today if not given.
        :param days_margin: Int - The number of days before from_date and after to_date to check for duplicates.
        :return: List of lists [
        [dup_count-Int, pub_id-Int, doi-Str, file_names-Str, deposit_dates-Str, note_ids-Str, metrics-Str, repo_ids-Int-List],
        ]
        """
        if to_date is None:
            to_date_obj = datetime.today()
            to_date = to_date_obj.strftime("%Y-%m-%d")
        else:
            to_date_obj = datetime.strptime(to_date, "%Y-%m-%d")
        if from_date is None:
            from_date_obj = to_date_obj - relativedelta(months=1)
            from_date = from_date_obj.strftime("%Y-%m-%d")
        else:
            from_date_obj = datetime.strptime(to_date, "%Y-%m-%d")

        if days_margin:
            relative_delta = relativedelta(days=days_margin)
            query_to_date = (to_date_obj + relative_delta).strftime("%Y-%m-%d")
            query_from_date = (from_date_obj - relative_delta).strftime("%Y-%m-%d")
        else:
            query_to_date = to_date
            query_from_date = from_date
        data_recs = []
        # Get list of tuples: [(dup_count, pub_id, doi, file_names, deposit_dates, note_ids, metrics, repo_ids),...]
        # Apart from dup_count which is Integer value, all other values are returned as Strings.
        # Note that repo_ids may be duplicated - so need de-duplication.
        for (dup_count, pub_id, doi, file_names, deposit_dates, note_ids, metrics, repo_ids)\
                in cls.bespoke_pull(query_from_date, query_to_date, pull_name="bspk_duplicate_submissions"):
            if days_margin:
                include = False
                for deposit_date in deposit_dates.split(', '):
                    # One of deposit dates is within our target range
                    if from_date <= deposit_date <= to_date:
                        include = True
                        break  # Exit deposit date loop
            else:
                include = True
            if include:
                # Keep this data row
                data_recs.append(
                    [dup_count,
                     int(pub_id),       # Pub Id converted to Int value
                     doi,
                     file_names,
                     deposit_dates,
                     note_ids,
                     metrics,
                     [int(v) for v in set(repo_ids.split(','))]  # Poss duplicated Repo-Ids string converted to List of Ints
                     ]
                )

        return data_recs


class FTPDepositRecord(PublisherDepositRecord):
    __type__ = "F"  # FTP


class APIDepositRecord(PublisherDepositRecord):
    __type__ = "A"  # API


class SwordInDepositRecord(PublisherDepositRecord):
    __type__ = "S"  # SWORD

    @property
    def in_progress(self):
        return self._get_single("sword_in_progress", coerce=dataobj.to_bool)

    @in_progress.setter
    def in_progress(self, value):
        self._set_single("sword_in_progress", value, coerce=dataobj.to_bool)


class PubTestRecord(dataobj.DataObj, PubTestRecordDAO):
    def __init__(self, raw=None, raw_trusted=True):
        """
        Model for a PublisherTestRecord - stores data about publisher test results)

        Field definitions:
        {
             "id": "<ID of this pub_deposit_record>",
             "pub_id": "<Publisher id of depositor>",
             "created": "<Date this record was created>",
             "fname": "<Name of file deposited in tmparchive>",
             "DOI": "<Name of file deposited in tmparchive>",
             "valid": "<Whether the submission was correctly processed>",
             "errors": [ "<Error messages if a failure occurs during processing>" ],
             "issues": [ "<Warning messages if problems during processing>" ],
             "route": "<One of 'ftp', 'api', 'sword', 'harv' depending on means of deposit>",
             "json_comp": "binary Base64 encoded compressed JSON string"
        }
        :param raw: raw data, a dictionary in a format like the one above. MUST have keys valid to the struct
            definition.
        :param raw_trusted: Boolean - True: Raw data comes from trusted source, like database; False: Raw data
                                      may not be OK, needs validating
        """
        struct = {
            "fields": {
                "id": {"coerce": "integer"},
                "pub_id": {"coerce": "integer"},
                "created": {"coerce": "utcdatetime"},
                "fname": {},
                "doi": {},
                "valid": {"coerce": "bool"},
                "route": {"allowed_values": ["ftp", "api"]},
                "json_comp": {"coerce": "unicode"}
            },
            "lists": {
                "errors": {"contains": "field"},
                "issues": {"contains": "field"},
            }
        }
        self._add_struct(struct)
        super().__init__(raw=raw, construct_raw=(not raw_trusted))

    @property
    def errors(self):
        return self._get_list("errors")

    @errors.setter
    def errors(self, value):
        # if scalar is passed, then convert to list before adding
        self._set_list("errors", value if isinstance(value, list) else [value])

    def add_error(self, value):
        self._add_to_list("errors", value)

    @property
    def issues(self):
        return self._get_list("issues")

    @issues.setter
    def issues(self, value):
        # if scalar is passed, then convert to list before adding
        self._set_list("issues", value if isinstance(value, list) else [value])

    @property
    def publisher_id(self):
        return self._get_single("pub_id")

    @publisher_id.setter
    def publisher_id(self, value):
        self._set_single("pub_id", value)

    @property
    def filename(self):
        return self._get_single("fname")

    @filename.setter
    def filename(self, value):
        self._set_single("fname", value)

    @property
    def doi(self):
        return self._get_single("doi")

    @doi.setter
    def doi(self, value):
        self._set_single("doi", value)

    @property
    def route(self):
        return self._get_single("route")

    @route.setter
    def route(self, value):
        self._set_single("route", value)

    @property
    def valid(self):
        return self._get_single("valid", coerce=dataobj.to_bool)

    @valid.setter
    def valid(self, value):
        self._set_single("valid", value, coerce=dataobj.to_bool)

    @property
    def json_comp(self):
        # Retrieve compressed binary value and return as string
        return self._get_single("json_comp")

    @json_comp.setter
    def json_comp(self, value):
        self._set_single("json_comp", value)

    def date_time_tuple(self):
        created = self.created
        return created[:10], created[11:19]

    @classmethod
    def publisher_test_recs(cls, publisher_id, page=1, page_size=None, with_json=False):
        """
        Gets test records for specified publisher, optionally limited by page and page_size if set.
        :param publisher_id: ID of  publisher
        :param page: OPTIONAL Page number (but must set page_size if used)
        :param page_size: OPTIONAL number of records per page (if None, then ES own default of 10 will apply)
        :param with_json: OPTIONAL Boolean - determines whether return the compressed Notification JSON from each record
        :return: List of PubTestRecord dicts returned by query
        """
        
        limit_offset = [page_size, (page - 1) * page_size] if page_size else None
        obj_list = cls.pull_all(publisher_id, pull_name="all_4_pub", limit_offset=limit_offset)
        if not with_json:
            for rec in obj_list:
                rec.data["json_comp"] = None
        return obj_list

    @classmethod
    def num_pub_test_recs(cls, publisher_id):
        """
        Return number of test records for publisher
        :param publisher_id:  ID of  publisher
        :return: Int - Number of records
        """
        return cls.count(publisher_id, pull_name="all_4_pub")
