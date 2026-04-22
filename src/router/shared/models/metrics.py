"""
Model for process metrics - which essentially record the time it took for a batch process to execute ("duration") in
seconds (to 3 decimal placs), together with a count of the number of 'things' processed.

Author: Jisc
"""
from time import time
from datetime import datetime, timezone
from flask import current_app
# from octopus.lib import dataobj
from router.shared.mysql_dao import MetricsRecordDAO


class MetricsRecord(MetricsRecordDAO):
    """
    Class represents a processing metrics record of the form:
        {
            "id": "<Unique sequential id>",
            "start": "<Process start timestamp - datetime object>",
            "duration": "<Process execution time in Seconds (to thousandths) NNNNN.NNN - floating point value>",
            "server": "<Server identifier - e.g. 'App1'>",
            "proc_name": "<Process name>",
            "measure": "<What is being counted>",
            "count": "<Number of things processed>"
            "extra": "<Dict of extra information>"
        }

        NOTE: Unlike other Router models, this class is NOT a subclass of octopus.lib.dataobj because its main purpose
        is to simply populate the database, so that external SQL queries can be run if required.

        Data for inserting into the database is stored as a Dict in self.data  (see MetricsRecordDAO and TableDAOMixin
        where self.data is initialised).
    """
    def _set_data(self, **kwargs):
        for k, v in kwargs.items():
            if k == "extra":
                # if extra dict provided, then save its contents separately
                for kk, vv in v.items():
                    self.data[kk] = vv
            elif k in ("start", "duration", "server", "proc_name", "measure", "count"):
                self.data[k] = v
            else:
                raise AttributeError(f"Parameter '{k}' is not valid.")

    def __init__(self, **kwargs):
        """
        Initialise metrics Object and set START time (if not passed as a parameter).
        :param **kwargs: All OPTIONAL
            raw: Dict  - complete dictionary of data with which to create record
            start: Float or Datetime - process start time
            proc_name: String - Process name
            count: Integer - number of items
            duration: Float - time taken to execute process in Seconds (to 3 decimal places)
            server: String - server name
            measure: String - what is being counted
            extra: Dict - Optional additional data
        """

        raw = kwargs.pop("raw", None)
        super(MetricsRecord, self).__init__(raw=raw)
        if raw is None:
            self._set_data(**kwargs)

        start = self.data.get("start")
        if start is None:
            self.start_time = time()
        else:
            # If start is present, and already a float then simply assign it, otherwise assume it is datetime object
            self.start_time = start if isinstance(start, float) else datetime.timestamp(start)

    def log_and_save(self, log_msg="", **kwargs):
        """
        Write INFO log entry and save process metric record.

        NOTE - `self.start_time` is ALWAYS set when Metrics() is instantiated (see __init__).

        :param log_msg: String - log message with optional placeholders for `count` and `s` (plural) values
        :param kwargs:
            start: Float or Datetime - process start time
            proc_name: String - Process name
            log_msg: String
            count: Integer - number of items
            server: String - server name
            measure: String - what is being counted
            extra: Dict - Optional additional data
        :return: Number of seconds to 3 decimal places
        """
        start = kwargs.pop("start", None)
        if start:
            # If start is present, and already a float then simply assign it, otherwise assume it is datetime object
            self.start_time = start if isinstance(start, float) else datetime.timestamp(start)
        self._set_data(**kwargs)
        rounded_secs = round(time() - self.start_time, 3)
        self.data["duration"] = rounded_secs
        count = self.data.get("count", 0)
        s = "" if count == 1 else "s"
        # Seconds is formatted to 3 decimal places
        current_app.logger.info(f"Completed {self.data['proc_name']} job" + log_msg.format(count, s) + f" in {rounded_secs:.3f} secs.")
        # Create start datetime obj as UTC time from start-time (float value)
        self.data["start"] = datetime.fromtimestamp(self.start_time, tz=timezone.utc)
        self.insert()
        return rounded_secs

    @classmethod
    def list_metrics(cls, page_num, page_size, min_count=0, from_date=None, to_date=None, proc_name=None):
        """
        Returns list of metrics records corresponding to passed parameters.

        Note that proc_name has 2 special values:
          "" - Return all metrics data for ALL process names
          "MAX" - Return MAX duration metrics for all process names
        :param page_num: Int - page number
        :param page_size: Int - Num of records per page
        :param min_count: Int - Minimum value of `count` field in record
        :param from_date: String - Start date ("YYYY-MM-DD" format)
        :param to_date: String - To date ("YYYY-MM-DD" format)
        :param proc_name: String - Name of process (or "MAX" or "")
        """
        def _convert_data(rec_tuple):
            """
            Convert certain elements of tuple into different data-type and return tuple as list.
              `rec_tuple` contains: (Start-date, Server, Process-name, Measure, Count, Number-secs, Number-mins, json-extra)
              with datatypes: (Datetime-obj, String, String, String, Int, Decimal-obj, Decimal-obj)
              * Start-date is converted to a String.
              * Number-secs & Number-mins decimal numbers are converted to Float values.

            :param rec_tuple: Record data - see above.
            """
            rec_list = list(rec_tuple)
            rec_list[0] = cls.datetime_to_str(rec_list[0], template="%Y-%m-%d %H:%M:%S")
            rec_list[5] = cls.convert_decimal(rec_list[5])
            rec_list[6] = cls.convert_decimal(rec_list[6])
            rec_list[7] = cls.dict_to_from_json_str(rec_list[7])
            return rec_list

        if from_date:
            if to_date is None:
                to_date = from_date
        # Special case - query to return MAX duration
        if proc_name == "MAX-ALL":
            if from_date:
                pull_name = "max_durations_range"
                # The query includes 2 lots of `DATE(start) BETWEEN ? AND ?` comparisons
                params = [from_date, to_date, from_date, to_date]
            else:
                pull_name = "max_durations"
                params = []
            total_recs = len(cls.bespoke_pull(pull_name="bspk_list_proc_names"))
        else:
            pull_name = ("range_with_count" if from_date else "all_with_count")
            params = [min_count]
            if from_date:
                params += [from_date, to_date]
            if proc_name:
                pull_name += "_of_type"
                params.append(proc_name)

            total_recs = cls.count(*params, pull_name=pull_name)

        # Bespoke pull returns list of tuples like (Start-date, Number-secs, Number-mins, Server, Process-name, Measure, Count)
        recs_list = [_convert_data(rec_tuple) for rec_tuple in cls.bespoke_pull(*params, pull_name=f"bspk_{pull_name}", limit_offset=[page_size, page_num * page_size])]
        return recs_list, total_recs
