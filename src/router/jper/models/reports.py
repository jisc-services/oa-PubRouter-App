"""
Models used for reporting

Author: Jisc
"""
from router.shared.mysql_dao import MonthlyInstitutionStatsDAO, MonthlyPublisherStatsDAO, MonthlyHarvesterStatsDAO

def process_pub_harv_data(rec_tuples, cal_year=True):
    """
    Retrieve monthly statistics between 2 dates (normally YYYY-01-01 to YYYY-12-01), returns list of dicts sorted in
    organisation name order.
    :param rec_tuples: List of tuples - Data returned by db query
    :param cal_year: Boolean - True: Full Calendar year (first date is Jan, last date is Dec); False: some other date range
    :return: List of dicts, each dict contains data for a particular organisation, and has the following structure
        [{"name": "organisation-name",
          "live_date": "YYYY-MM-DD" or None,
          "Jan": (metadata_count, content_count), *
          "Feb": (metadata_count, content_count), *
          ...
          }
        ]
        NOTE: * - Months will only be present where the data exists
    """
    date_format = "%b" if cal_year else "%Y-%b"  # Either Jan, Feb, Mar etc. or YYYY-Jan, YYYY-Feb etc.
    ret_list = []
    curr_acc_id = None
    org_dict = {}
    for org_name, ymd_obj, received_count, matched_count, acc_id in rec_tuples:
        # If new organisation
        if acc_id != curr_acc_id:
            if curr_acc_id is not None:
                # Save previous org's data
                ret_list.append(org_dict)
            curr_acc_id = acc_id
            org_dict = {"id": acc_id, "name": org_name}
        org_dict[ymd_obj.strftime(date_format)] = (received_count, matched_count)
    # Last entry
    if org_dict:
        ret_list.append(org_dict)
    return ret_list


class MonthlyInstitutionStats(MonthlyInstitutionStatsDAO):
    """
    Monthly Institution reporting statistics methods for:
        - creating statistics summary records for a particular month (normally month just passed)
        - retrieving reporting data for specified period (normally a calendar year)
    """
    @classmethod
    def create_monthly_stats_records(cls, month_start, month_end):
        """
        Creates monthly statistics records in `monthly_institution_stats` table for each Institution account from
        notification records accumulated during the specified month (typically the month just passed).
        :param month_start: Date object - First day of the month
        :param month_end: Date object - Last day of the month
        :return: Number of records created
        """

        # NOTE: Each bespoke insert query takes 3 date parameters as coded below

        # Insert monthly statistics for each Live repository account
        # Because we only use this cursor once a month, it does not make sense to keep it open
        num_recs_1 = cls.bespoke_insert(month_start, month_start, month_end,
                                        data_vals=[],
                                        query_name="insert_live_monthly_by_ac",
                                        close_cursor=True)

        # Insert monthly statistics for each Test repository account
        # Because we only use this cursor once a month, it does not make sense to keep it open
        num_recs_2 = cls.bespoke_insert(month_start, month_start, month_end,
                                        data_vals=[],
                                        query_name="insert_test_monthly_by_ac",
                                        close_cursor=True)

        # Insert monthly unique statistics for all Live repository accounts
        # Because we only use this cursor once a month, it does not make sense to keep it open
        num_recs_3 = cls.bespoke_insert(month_start, month_start, month_end,
                                        data_vals=[],
                                        query_name="insert_live_monthly_unique",
                                        close_cursor=True)

        # Insert monthly unique statistics for all Test repository accounts
        # Because we only use this cursor once a month, it does not make sense to keep it open
        num_recs_4 = cls.bespoke_insert(month_start, month_start, month_end,
                                        data_vals=[],
                                        query_name="insert_test_monthly_unique",
                                        close_cursor=True)

        return num_recs_1 + num_recs_2 + num_recs_3 + num_recs_4


    @classmethod
    def get_stats_between_2_dates(cls, type_l_or_t, first_date, last_date, cal_year=True):
        """
        Retrieve monthly statistics between 2 dates (normally YYYY-01-01 to YYYY-12-01), returns list of dicts sorted in
        organisation name order.
        :param type_l_or_t: String - "L" for Live accounts; "T" for Test accounts
        :param first_date: Date object - first date
        :param last_date: Date object - last date
        :param cal_year: Boolean - True: Full Calendar year (first date is Jan, last date is Dec); False: some other date range
        :return: List of dicts, each dict contains data for a particular organisation, and has the following structure
            [{"id": acc-id,
              "name": "organisation-name",
              "live_date": "YYYY-MM-DD" or None,
              "Jan": (metadata_count, content_count), *
              "Feb": (metadata_count, content_count), *
              ...
              }
            ]
            NOTE: * - Months will only be present where the data exists
        """
        date_format = "%b" if cal_year else "%Y-%b"     # Either Jan, Feb, Mar etc. or YYYY-Jan, YYYY-Feb etc.
        ret_list = []
        # Returns a List of tuples [(org_name, ymd-date-object, repo-name, metadata-only-count, with-content-count, acc-ID, acc-live-date-string), ...]
        # Sorted by org_name, then year-month-date
        # No need to use a scroller here as expect relatively few records to be retrieved
        rec_tuples = cls.bespoke_pull(type_l_or_t, first_date, last_date,
                                      pull_name="bspk_repo_annual_data",
                                      close_cursor=True)

        curr_acc_id = None
        org_dict = {}
        for org_name, ymd_obj, repo_name, metadata_count, content_count, acc_id, live_date_str, r_identifiers in rec_tuples:
            # If new organisation
            if acc_id != curr_acc_id:
                if curr_acc_id is not None:
                    # Save previous org's data
                    ret_list.append(org_dict)
                curr_acc_id = acc_id
                if acc_id == 0:
                    org_name = "Unique"
                jisc_id = None
                # Get the JISC id from r_identifiers list of dicts
                for ident in cls.list_to_from_json_str(r_identifiers, to_db=False):
                    if ident["type"] == "JISC":
                        jisc_id = ident["id"]
                        break
                org_dict = {"id": acc_id, "name": org_name, "repo": repo_name, "live_date": live_date_str, "jisc_id": jisc_id}
            org_dict[ymd_obj.strftime(date_format)] = (metadata_count, content_count)
        # Last entry
        if org_dict:
            ret_list.append(org_dict)
        return ret_list


class MonthlyPublisherStats(MonthlyPublisherStatsDAO):
    """
    Monthly Publisher reporting statistics methods for:
        - creating statistics summary records for a particular month (normally month just passed)
        - retrieving reporting data for specified period (normally a calendar year)
    """
    @classmethod
    def create_monthly_stats_records(cls, month_start, month_end):
        """
        Creates monthly statistics records in `monthly_publisher_stats` table for each publisher account from
        publisher deposit history records accumulated during the past month in pub_deposit table.
        :param month_start: Date object - First day of the month
        :param month_end: Date object = Last day of the month
        :return: Number of records created
        """
        # The bespoke insert query takes 3 date parameters as shown here
        # Because we only use this cursor once a month, it does not make sense to keep it open
        num_recs = cls.bespoke_insert(month_start, month_start, month_end,
                                      data_vals=[],
                                      query_name="insert_pub_monthly_stats",
                                      close_cursor=True)
        return num_recs

    @classmethod
    def get_stats_between_2_dates(cls, first_date, last_date, cal_year=True):
        """
        Retrieve monthly statistics between 2 dates (normally YYYY-01-01 to YYYY-12-01), returns list of dicts sorted in
        organisation name order.
        :param first_date: Date object - first date
        :param last_date: Date object - last date
        :param cal_year: Boolean - True: Full Calendar year (first date is Jan, last date is Dec); False: some other date range
        :return: List of dicts, each dict contains data for a particular organisation, and has the following structure
            [{"id": acc-id,
              "name": "organisation-name",
              "Jan": (metadata_count, content_count), *
              "Feb": (metadata_count, content_count), *
              ...
              }
            ]
            NOTE: * - Months will only be present where the data exists
        """
        # No need to use a scroller here as expect relatively few records to be retrieved
        return process_pub_harv_data(cls.bespoke_pull(first_date, last_date,
                                                      pull_name="bspk_pub_annual_data",
                                                      close_cursor=True),
                                     cal_year=cal_year)


class MonthlyHarvesterStats(MonthlyHarvesterStatsDAO):
    """
    Monthly Harvester reporting statistics methods for:
        - creating statistics summary records for a particular month (normally month just passed)
        - retrieving reporting data for specified period (normally a calendar year)
    """

    @classmethod
    def create_monthly_stats_records(cls, month_start, month_end):
        """
        Creates monthly statistics records in `monthly_harvester_stats` table for each WebService from
        harvester history records accumulated during the past month in h_history table.
        :param month_start: Date object - First day of the month
        :param month_end: Date object = Last day of the month
        :return: Number of records created
        """
        # The bespoke insert query takes 5 date parameters as shown here
        # Because we only use this cursor once a month, it does not make sense to keep it open
        num_recs = cls.bespoke_insert(month_start, month_start, month_end, month_start, month_end,
                                      data_vals=[],
                                      query_name="insert_harv_monthly_stats",
                                      close_cursor=True)
        return num_recs


    @classmethod
    def get_stats_between_2_dates(cls, first_date, last_date, cal_year=True):
        """
        Retrieve monthly statistics between 2 dates (normally YYYY-01-01 to YYYY-12-01), returns list of dicts sorted in
        organisation name order.
        :param first_date: Date object - first date
        :param last_date: Date object - last date
        :param cal_year: Boolean - True: Full Calendar year (first date is Jan, last date is Dec); False: some other date range
        :return: List of dicts, each dict contains data for a particular organisation, and has the following structure
            [{"id": acc-id,
              "name": "organisation-name",
              "Jan": (metadata_count, content_count), *
              "Feb": (metadata_count, content_count), *
              ...
              }
            ]
            NOTE: * - Months will only be present where the data exists
        """
        # No need to use a scroller here as expect relatively few records to be retrieved
        return process_pub_harv_data(cls.bespoke_pull(first_date, last_date,
                                                      pull_name="bspk_harv_annual_data",
                                                      close_cursor=True),
                                     cal_year=cal_year)

