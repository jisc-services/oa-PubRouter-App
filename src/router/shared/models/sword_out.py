"""
Models for representing the sword objects supporting the deposit run
"""
from octopus.lib import dataobj
from router.shared.mysql_dao import SwordDepositRecordDAO, ReportingHelperMixin

# Status options
FAILED = 0
DEPOSITED = 1

# scroll_num values: help ensure that Scrollers use unique connections (though uniqueness is conferred by scroll_name
# which is a composite of scroll_num, pull_name and other attributes).
# IMPORTANT check entire code base for other similar declarations before adding new ones (or changing these numbers) to
# avoid overlaps - do global search for "_SCROLL_NUM ="
SWORD_DEPOSIT_SCROLL_NUM = 15


class SwordDepositRecord(dataobj.DataObj, SwordDepositRecordDAO, ReportingHelperMixin):
    """
    Class to represent the record of a SWORD deposit of a single notification to a repository

    Of the form:
    ::
        {
            "id": "<opaque id of the deposit - also used as the local store id for the response content>",
            "deposit_date": "<date of attempted deposit>",
            "note_id": "<notification id that the record is about>",
            "repo_id": "<account id of the repository>",
            "metadata_status": "<deposited|failed>",
            "content_status": "<deposited|none|failed>",
            "completed_status": "<deposited|none|failed>"
            "error_message": "<error_message if there is any problem sending the notification to a repository>"
            "doi": "<deposited article DOI>",
            "edit_iri": "<Location of deposit in repository - International resource identifier (cf URI)>",
            "err_emailed": "<Boolean indicates whether error has been included in an email sent to account contact>"
        }
    """
    def __init__(self, raw=None):
        """
        Create a new instance of the SwordDepositRecord object, optionally around the
        raw python dictionary.

        If supplied, the raw dictionary will be validated against the allowed structure of this
        object, and an exception will be raised if it does not validate

        :param raw: python dict object containing the metadata
        """
        struct = {
            "fields": {
                "id": {"coerce": "integer"},
                "deposit_date": {"coerce": "utcdatetime"},
                "note_id": {"coerce": "integer"},
                "repo_id": {"coerce": "integer"},
                "metadata_status": {"coerce": "integer"},   # "allowed_values": [DEPOSITED, FAILED]},
                "content_status": {"coerce": "integer"},    # "allowed_values": [DEPOSITED, FAILED, None]},
                "completed_status": {"coerce": "integer"},  # "allowed_values": [DEPOSITED, FAILED, None]},
                "error_message": {},
                "doi": {},
                "edit_iri": {"coerce": "unicode"},
                "err_emailed": {"coerce": "bool"}
            }
        }

        # self._add_struct(struct)
        super(SwordDepositRecord, self).__init__(raw=raw, struct=struct)

    @property
    def doi(self):
        return self._get_single("doi")

    @doi.setter
    def doi(self, val):
        self._set_single("doi", val)

    @property
    def repository(self):
        """
        The repository account id this deposit was to

        :return: account id
        """
        return self._get_single("repo_id")

    @repository.setter
    def repository(self, val):
        """
        Set the repository account id

        :param val: account id
        :return:
        """
        self._set_single("repo_id", val, coerce=dataobj.to_unicode)

    @property
    def notification(self):
        """
        The notification id that was deposited

        :return: notification id
        """
        return self._get_single("note_id")

    @notification.setter
    def notification(self, val):
        """
        Set the notification id that was deposited

        :param val: notification id
        :return:
        """
        self._set_single("note_id", val, coerce=dataobj.to_unicode)

    @property
    def deposit_date(self):
        """
        get the deposit date of the notification, as a string of the form YYYY-MM-DDTHH:MM:SSZ

        :return: deposit date
        """
        return self._get_single("deposit_date")

    @deposit_date.setter
    def deposit_date(self, val):
        """
        set the deposit date, as a string of the form YYYY-MM-DDTHH:MM:SSZ

        :param val:deposit date
        :return:
        """
        self._set_single("deposit_date", val, coerce=dataobj.date_str())

    @property
    def deposit_datestamp(self):
        """
        Get the deposit date of the notification as a datetime object

        :return: deposit date
        """
        return self._get_single("deposit_date", coerce=dataobj.to_datetime_obj())

    @property
    def metadata_status(self):
        """
        Get the status of the metadata deposit.  deposited or failed

        :return: metadata deposit status
        """
        return self._get_single("metadata_status")

    @metadata_status.setter
    def metadata_status(self, val):
        """
        Set the status of the metadat adeposit.  Must be one of "deposited" or "failed"

        :param val: metadata deposit status
        :return:
        """
        self._set_single("metadata_status", val, allowed_values=[DEPOSITED, FAILED])

    @property
    def content_status(self):
        """
        Get the status of the content deposit.  deposited, none or failed

        :return: content deposit status
        """
        return self._get_single("content_status")

    @content_status.setter
    def content_status(self, val):
        """
        Set the content deposit status.  Must be one of "deposited", "none" or "failed"

        :param val: content deposit status
        :return:
        """
        self._set_single("content_status", val, allowed_values=[DEPOSITED, FAILED, None])

    @property
    def completed_status(self):
        """
        Get the status of the completion request.  deposited, none or failed

        :return: completion request status
        """
        return self._get_single("completed_status")

    @completed_status.setter
    def completed_status(self, val):
        """
        Set the completed request status.  Must be one of "deposited", "none" or "failed"

        :param val: completed request status
        :return:
        """
        self._set_single("completed_status", val, allowed_values=[DEPOSITED, FAILED, None])

    @property
    def error_message(self):
        """
        Get the error message when the status is failed

        :return: error message
        """
        return self._get_single("error_message")

    @error_message.setter
    def error_message(self, val):
        """
        Set the error message when the status is failed

        :param val: error message
        :return:
        """
        self._set_single("error_message", val, coerce=dataobj.to_unicode)

    @property
    def edit_iri(self):
        """
        Get the edit_iri (URI to deposit in repository)
        :return: Edit IRI
        """
        return self._get_single("edit_iri")

    @edit_iri.setter
    def edit_iri(self, val):
        """
        Set the edit_iri (URI to deposit in repository)

        :param val: edit IRI
        :return:
        """
        self._set_single("edit_iri", val)

    def was_successful(self):
        """
        Determine whether this was a successful deposit or not.

        A deposit is considered successful if metadata_deposit is "deposited".

        Content_status and completed_status are ignored to avoid generating duplicate entries in repositories.

        :return: True if successful, False if not
        """
        return self.metadata_status == DEPOSITED

    @classmethod
    def pull_most_recent_by_note_id_and_repo_id(cls, note_id, repo_id):
        """
        Get most recent record matching note_id and repo_id. for which metadata_status is DEPOSITED
        @param note_id: Int - Notification ID
        @param repo_id: Int - Repository ID
        @return: Record or None
        """
        recs = cls.pull_all(note_id, repo_id, pull_name="by_note_id_repo_id_meta_ok", limit_offset=1, order_by="desc")
        return recs[0] if recs else None

    @classmethod
    def retrieve_deposited_by_acc_and_doi(cls, repo_id, doi, latest_first=True):
        """
        Retrieve deposit records associated repository_id and DOI, sorted by deposit_date (ascending or descending).
        Only those with successful metadata deposits are retrieved (these could have failed content deposits).

        :param repo_id: Unique ID of repository
        :param doi: DOI
        :param latest_first: Boolean - True: sort descending (newest first); False: sort ascending (oldest first)
        :return: List of SwordDepositRecord objects
        """
        return cls.pull_all(repo_id, doi, pull_name="by_repo_id_and_doi", order_by="desc" if latest_first else "asc")

    @classmethod
    def aggregate_sword_deposit_daily(cls,
                                      repo_id,
                                      from_date=None,
                                      to_date=None,
                                      page=None,
                                      page_size=None,
                                      do_count=True,
                                      rec_format=None,
                                      col_headings=None,
                                      ):
        """
        Aggregates sword_deposit_records into daily statistics, producing for each date a record containing:
            Date
            Count of sword-deposit records
            Count of successful metadata deposits
            Count of failed metadata deposits
            Count of successful fulltext file deposits
            Count of failed fulltext file deposits
            String "|" separated list of error messages that include the notification ID
        :param repo_id: Int - repository ac ID
        :param from_date: String "YYYY-MM-DD" - Date from which data reqd
        :param to_date: String "YYYY-MM-DD" - Date to which data reqd
        :param page: page number in result set to return
        :param page_size: number of results to return in this page of results
        :param do_count: Boolean - True: Calculate total count; False: Don't necessarily calculate total
        :param rec_format: Integer (dao.RAW, dao.DICT, dao.WRAP) or a reference to a formatting function
        :param col_headings: List of Strings - column headings OR None
        :return: Tuple - (Count-of-total-recs, DAOScroller object for iterating over records. column-headings-list or None)
        """
        count, scroller = cls.aggregate_over_time_period(
            repo_id, pull_name="bspk_daily_for_repo", to_date=to_date, from_date=from_date, page=page,
            page_size=page_size, do_count=do_count, rec_format=rec_format, scroll_num=SWORD_DEPOSIT_SCROLL_NUM)
        return count, scroller, col_headings

    @classmethod
    def recs_scroller_for_csv_file(cls, repo_id, from_date=None, to_date=None, page=None, page_size=None):
        """
        Simple method to convert a list of aggregate buckets to a csv-writable list of tuples for use on the
        SWORD deposit history page.

        :param repo_id: ID of the repository we want to get statistics about
        :param from_date: String "YYYY-MM-DD" - Minimum date we want to have statistics for. If not supplied, will
                            take everything until the to_date (so, anything that is before the to_date.)
        :param to_date: String "YYYY-MM-DD" - Date maximum date we want to have statistics for. Will default to today.
        :param page: page number in result set to return
        :param page_size: number of results to return in this page of results

        :return: Tuple - (Count-of-total-recs, DAOScroller object for iterating over records. column-headings-list)
        """
        def format_rec(rec_tuple):
            row = list(rec_tuple[0:6])
            row.append(ReportingHelperMixin.reformat_array_string(rec_tuple[6]))
            return row

        return cls.aggregate_sword_deposit_daily(
            repo_id, from_date, to_date, page, page_size, do_count=False, rec_format=format_rec,
            col_headings=["Date", "Total", "Metadata OK", "Metadata Failed", "Fulltext OK", "Fulltext Failed", "Errors"]
        )

    @classmethod
    def get_formatted_errors_for_id_list(cls, sword_deposit_ids):
        """
        Return list of dates & formatted error tuples for given ids [(date, formatted-error), ...]
        """
        # bespoke_pull returns list of tuples - we expect a single element list with a 2 element tuple
        # (date, formatted-error) for each Id
        # No need to use a scroller here as expect relatively few, small records to be retrieved
        return [cls.bespoke_pull(id, pull_name="bspk_errmsg_by_id")[0] for id in sword_deposit_ids]

    @classmethod
    def update_to_indicate_errors_emailed(cls, sword_deposit_ids):
        """
        Update records to show that error included in email
        """
        for id in sword_deposit_ids:
            cls.bespoke_update(id, query_name="update_err_emailed_true")
