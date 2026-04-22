"""
Code to provide a database stored schedule & associated scheduling of jobs, which allows jobs to be synchronised across
server and/or executable programs (including the ability to trigger a job on a different server, and prevent jobs
on different servers from running in parallel).

The schedule spec is defined in configuration as a List of job entries of this form:

Example schedule_spec:
    SCHEDULER_SPEC = [
        # ("Label (unique)", "start-time", interval (mins-integer or string like '10s', '20m' or '3h'), "end-time", "function-name", priority (1 to 4), "trigger-label(s)" (string or list of strings))
        # NB. If there is no interval then job will be 1-off UNLESS it is triggered by another job

        # 1-off job with priority 2 (HIGH), starting at 00:15, triggers "RH1" on completion
        ("HA1", "00:15", None, None, "harvest", 2, "RH1"),
        # 1-off job with priority 2 (HIGH), running at 01:00 (if not previously triggered), triggers "SO1" & "MF2" on completion
        ("RH1", "01:00", None, None, "route_harv", 2, ["SO1", "MF2-always"]),
        # Job with default priority (MEDIUM), cannot run after 03:00. Must be triggered to run.
        ("SO1", None, None, "03:00", "sword_out", None, None),
        # Job with default priority (MEDIUM), running at 01:30 (if not previously triggered) and every 30 mins (from last run time) until 03:00
        ("MF2", "01:30", 30, "03:00", "move_ftp", None, "PF2"),
        # Job with default priority (MEDIUM), cannot run after 03:00, triggers "R02" on completion. Must be triggered to run.
        ("PF2", None, None, "03:00", "process_ftp", None, "RO2"),
        # Job with default priority (MEDIUM), running every 30 mins (from last run time) until 03:00. Must be triggered to run.
        ("RO2", None, 30, "03:00", "route", None, "SO1"),  # This may route a lot of IOP stuff
        # One-off job with priority 2 (HIGH), running at 03:55
        ("", "03:55", None, None, "delete_files", 2, None),
        # One-off job with priority 2 (HIGH), running at 04:04
        ("", "04:04", None, None, "delete_old", 2, None),
        # One-off job with default priority (MEDIUM), running at 04:12
        ("", "04:12", None, None, "monthly_jobs", None, None),
        # One-off job with priority 1 (VERY HIGH), running at 04:28
        ("", "04:28", None, None, "shutdown", 1, None),
        # Job with default priority (MEDIUM), running every 30 secs (from last run time) from 08:00 until 23:59, triggers "PF3"
        ("MF3", "08:00", "30s", "23:59", "move_ftp", None, "PF3"),
        # Default priority job, cannot run after 23:59, triggers "RO3" on completion. Must be triggered to run.
        ("PF3", None, None, "23:59", "process_ftp", None, "RO3"),
        # Default priority job, running every 30secs from last run time, cannot run after 23:59, triggers "SO3" on completion. First run must be triggered.
        ("RO3", None, "30s", "23:59", "route", None, "SO3"),
        # Default priority job, running every 5 minutes from last run time, cannot run after 23:59.
        ("SO3", None, 5, "23:59", "sword_out", None, None),
    ]

IMPORTANT NOTES:
* The Function-Name of the job that terminates a running application should be "shutdown" in order to avoid generating
  WARNING log messages that would otherwise result from schedule records being deleted from the database.
* Only 1 schedule (shared across all application processes and servers) is currently supported.  In order to support
  different schedules for different processes it would be necessary to add a `schedule` parameter and
  corresponding database column in `job` table, and modify the table indexes to include this column as first element,
  and modify the queries (defined in JobDAO) to include the `schedule` name so that only jobs for a particular schedule
  are retrieved / deleted / updated etc.
* By default the schedule will be reloaded (from config) just after midnight each day, but this can be avoided by
  setting parameter new_day_reload=False if the application is terminated (shutdown) once a day (which renders
  automatic reload unnecessary).

Author: Jisc
"""
from time import sleep
from datetime import datetime, timedelta, timezone
from logging import CRITICAL, ERROR, WARNING, INFO, DEBUG
from octopus.lib import dataobj
from router.shared.mysql_dao import JobDAO

# Status
TRIGGERED = 1   # Job ready to start - has been triggered by another job
PENDING = 2     # Job ready to start
WAITING=3       # Job ready, but waiting for a conflicting job
RUNNING = 5     # Job in progress
FINISHED = 9    # Job has finished, but possible it could be triggered in future
ENDED = 99      # Job can never be run as current time is later than end time

# Priority
PRIMER = 0  # Special priority used for primer jobs - these are jobs created on one server to trigger a job on another
V_HIGH = 1
HIGH = 2
MEDIUM = 3  # DEFAULT value
LOW = 4
NEVER = 99  # Special priority - set when a job has ENDED

far_future = datetime.max.replace(tzinfo=timezone.utc)
one_day = timedelta(days=1)


def _get_dict_entry(d, k, upper, default="None"):
    s = d.get(k, default)
    return s.upper() if upper else s


def status_str(status, default="", upper=False):
    """
    Convert a Status integer value into description string.
    :param status: Int - status value
    :param default: String - value to return if `status` is None or bad value
    :param upper: Boolean - True: return UPPER CASE; False: return Title case
    :return: String - Status description word
    """
    return _get_dict_entry(
        {TRIGGERED: "Triggered", PENDING: "Pending", WAITING: "Waiting", RUNNING: "Running", FINISHED: "Finished", ENDED: "Ended"},
        status, upper, default)


def priority_str(priority, upper=False):
    """
    Convert Priority integer value into description string.
    :param priority: Int - priority value
    :param upper: Boolean - True: return UPPER CASE; False: return Title case
    :return: String - Priority description
    """
    return _get_dict_entry(
        {PRIMER: "Primer", V_HIGH: "Very high", HIGH: "High", MEDIUM: "Medium", LOW: "Low", NEVER: "Never"},
        priority, upper)


def construct_process_map(master_process_map=None, jobs_list=None):
    """
    Construct a process_map from master_process_map and jobs_list.

    :param master_process_map: Dict - {"job-name": function, "job-keyword-2": func-2, ...}
    :param jobs_list: List of job-name Strings - ["job-name", ...,] corresponding to keys in master_process_map which
            identify the jobs to be run by the current program's Schedule.
    :return: process_map dict (same structure as `master_process_map`) or may raise a ValueError
    """
    if not isinstance(master_process_map, dict):
        raise ValueError("Parameter master_process_map dict not provided - see construct_process_map()")
    process_map = {}
    if not jobs_list:
        process_map = master_process_map.copy()
        jobs_list = list(process_map.keys())
        print("\n-- Defaulting to ALL scheduler jobs")
    else:
        bad_args = []
        for job in jobs_list:
            fn = master_process_map.get(job)
            if fn is None:
                bad_args.append(job)
            else:
                # print(f"Arg: {job}")
                process_map[job] = fn
        if bad_args:
            print(f"\nERROR: Job keyword(s) not recognised: {bad_args}.\n"
                  f"Only the following values are allowed: {list(master_process_map.keys())}.\n")
            raise ValueError(f"ERROR: Job keyword(s) not recognised: {bad_args}.")

    print(f"\n--Scheduler may run these processes: {jobs_list} (depending on SCHEDULER_SPEC) ---\n")
    return process_map


def set_timedelta_from_str_or_int(frequency_str_or_int):
    """
    Create a `timedelta` object (representing a frequency/periodicity) from an Integer (num minutes) or a
    String (number of hours or minutes or seconds).
    :param frequency_str_or_int: Int - number of Minutes or
                             String - A number of Hours, Minutes or Seconds, expressed as "99h" or "99m" or "99s"
    :return: timedelta object or raise exception if unexpected format
    """
    if isinstance(frequency_str_or_int, int):
        return timedelta(minutes=frequency_str_or_int)

    # If we get this far `frequency_str_or_int` assumed to be a string of form: "9h" or "88m" or "777s"
    if len(frequency_str_or_int) > 1:
        kw = {"s": "seconds", "m": "minutes", "h": "hours"}.get(frequency_str_or_int[-1].lower())
        if kw:
            return timedelta(**{kw: int(frequency_str_or_int[:-1])})
    raise ValueError("If periodicity is a string, it must be an integer followed by 's', 'm' or 'h'. E.g. '20s' or '10m' or '3h'.")


class NoJobsScheduled(Exception):
    """
    No jobs scheduled for this particular executable program.  (Jobs may be scheduled for other programs)
    """
    pass


class EndSchedule(BaseException):
    """
    Optional base exception that indicates Schedule is to be terminated
    NOTE: Extends 'BaseException' so will NOT be caught by a general Exception block.
    """
    pass


class PurgeSchedule(EndSchedule):
    """
    Optional base exception that indicates Schedule is to be terminated and ALL job records deleted.
    NOTE: Extends 'BaseException' so will NOT be caught by a general Exception block.
    """
    pass


class JobResult:
    """
    Class used to return results of job execution.
    """
    END_JOB  = 1        # Prevent job from running again (i.e. being triggered or automatically repeating)
    END_SCHEDULE = 7    # Terminate the Scheduler (infinite) loop - set by a Job
    PURGE_SCHEDULE = 8  # Terminate the Scheduler (infinite) loop &, subsequently, cause ALL scheduler Jobs to be
                        # deleted (table to be truncated) - set by a Job
    KILL_SCHEDULE = 9   # Terminate the Scheduler (infinite) loop - caused by KeyboardInterrupt or similar kill signal

    _flag_desc = {
        END_JOB: "END_JOB",
        END_SCHEDULE: "END_SCHEDULE",
        PURGE_SCHEDULE: "PURGE_SCHEDULE",
        KILL_SCHEDULE: "KILL_SCHEDULE",
        None: "None"
    }

    _end_cause = {
        END_SCHEDULE: "ended by",
        PURGE_SCHEDULE: "purged by",
        KILL_SCHEDULE: "killed during",
        None: ""
    }

    def __init__(self, job_name="", count=None, func_return=None, job_flag=None, exception=None, after_run_action_fn=None):
        """

        :param job_name: String - Name of job (function) that was run
        :param count: Integer - Count of items processed
        :param func_return: Variable - all values returned by job function (if more than just count)
        :param job_flag: Integer - special flag interpreted by scheduler - one of END_JOB, END_SCHEDULE, PURGE_SCHEDULE, KILL_SCHEDULE
        :param exception: Exception raised by function, which the Scheduler will then raise after completing job updates
        :param after_run_action_fn: Function to execute (in all circumstances) after a job has run - use cautiously...
                            IMPORTANTLY: this runs AFTER updating the Jobs db record & AFTER triggering any follow-on
                            jobs.  It is intended for such activities as doing a database reset.
        """
        self.job_name = job_name
        self.count = count
        self.func_return = func_return
        self.job_flag = job_flag
        self.exception = exception
        self.after_run_action_fn = after_run_action_fn

    def __str__(self):
        return f"Function: {self.job_name}; Count: {self.count}; Return: {self.func_return}; Flag: {self._flag_desc.get(self.job_flag, 'Invalid flag')}; Exception: {repr(self.exception)}; After run func: {self.after_run_action_fn.__name__ if self.after_run_action_fn else 'None'}"

    def __repr__(self):
        return f"{self.__class__.__name__} ({self.__str__()})"

    def describe(self, fields="NCRFEA", exc_name_only=True):
        """
        Produce a string describing the Job Result. Fields to be included in the description can be specified.
        Only none empty values are included in the returned description.

        :param fields: String of characters from set [N, C, R, F, E, A] which determine which fields may be returned
                        in the description.
        :param exc_name_only: Boolean - True: [DEFAULT] Return only the exception class name;
                                        False: Return full repr(exception)
        :return: String of semicolon separated values
        """
        ret = []
        for f in fields:
            if f == "N":
                ret.append(f"Func: {self.job_name}")
            elif f == "C" and self.count is not None:
                ret.append(f"Count: {self.count}")
            elif  f == "R" and self.func_return:
                ret.append(f"Ret: {self.func_return}")
            elif f == "F" and self.job_flag:
                ret.append(f"Flag: {self._flag_desc.get(self.job_flag, 'Invalid flag')}")
            elif f == "E" and self.exception:
                ret.append(f"Exception: {self.exception.__class__.__name__ if exc_name_only else repr(self.exception)}")
            elif f == "A" and self.after_run_action_fn:
                ret.append(f"After func: {self.after_run_action_fn.__name__}")
        return "; ".join(ret)

    def schedule_end_cause(self):
        return self._end_cause.get(self.job_flag, "")

    def end_schedule(self):
        """
        If end schedule is required, return the job flag (one of END_SCHEDULE, KILL_SCHEDULE or PURGE_SCHEDULE)
        otherwise return None.
        :return: END_SCHEDULE, KILL_SCHEDULE, PURGE_SCHEDULE or None
        """
        return self.job_flag if self.job_flag and self.job_flag >= self.END_SCHEDULE else None

    @classmethod
    def schedule_end_exception(cls, job_flag, msg):
        """
        Return the appropriate Schedule Base Exception instance PurgeSchedule() or EndSchedule()
         """
        return PurgeSchedule(msg) if job_flag == cls.PURGE_SCHEDULE else EndSchedule(msg)


class Schedule:
    """
    Class that runs a timed schedule of jobs.  Allows for one job to trigger another.  Jobs are queued, and once a
    job's next start time is reached it will then be executed at the earliest opportunity (after any higher priority
    jobs and any conflicting jobs - which cannot be run in parallel -  have completed).  Jobs in the schedule can be
    run by different programs and on different servers (this is enabled by saving them in the database).
    """
    current_time = None
    priority_order = (V_HIGH, HIGH, MEDIUM, LOW)

    def __init__(self, server, prog, schedule_spec, conflicts_dict, process_map,
                 sleep_secs=None, logger=None, raise_end_schedule=False, end_if_no_jobs=True, defer_end=None, new_day_reload=True):
        """
        Initialise a Schedule.

        :param server: String - Unique name for the particular server the schedule is running on, ideally length <= 6.  E.g. "App1"
        :param prog: String - Unique name for the particular program that is running schedule, ideally length <= 6.  E.g. "Sched" or "Harv"
        :param schedule_spec: - List of Tuples that define the daily schedule - see example at top of file.
        :param conflicts_dict: - Dict identifying particular functions (jobs) by function-name that shouldn't run simultaneously
        :param process_map: Dict - Maps function-name to actual function to execute e.g. {"func-name": func, ...}
        :param sleep_secs: Integer - Number of seconds to sleep between successive calls to `run_next_pending`-job,
                DEFAULTS to 5. `
        :param logger: Object - Logger for outputting info (if none provided then log items will be printed)
        :param raise_end_schedule: Boolean - Whether to raise EndSchedule (base exception) upon end-schedule event OR
                            not (in which case end-flag is returned) [DEFAULT]
        :param end_if_no_jobs: Boolean - Action to take if no active job records found for current process in database -
                        True [DEFAULT] - End the schedule (will normally result in application being exited);
                        False - Re-initialise the schedule - BUT if still no active jobs, the schedule will then end.
        :param defer_end: If END_SCHEDULE flag is set then defer actual ending until either ALL primer jobs created
                        by this server-prog have been actioned (& therefore deleted) or the maximum deferment time
                        has expired.  Allowed values:
                            None - NO deferment (end immediately)
                            Integer number of minutes, OR
                            String like '10s', '20m' or '3h'.
        :param new_day_reload: Boolean - True: Automatically reload schedule after midnight; False: No auto-reload

        Will raise a NoJobsScheduled exception if there are no jobs for this server program
        """
        if not server or not prog:
            raise ValueError("Both `server` and `prog` parameters are required.")
        server_prog = f"{server}.{prog}"
        if len(server_prog) > 25:
            raise ValueError("The combined length of `server` and `prog` strings must be <= 25.")
        if sleep_secs is not None and not 1 <= sleep_secs <= 60:
            raise ValueError("In Schedule() the 'sleep_secs' parameter should be between 1 and 60 (seconds)")
        self.sorted_jobs = {}   # dict of lists of jobs for each priority level
        self._clear_sorted_jobs()   # Initialise the self.sorted_jobs dict
        self.primed_jobs = {}   # records "primer jobs" (which trigger jobs on another server), that were originally created on this server
        self.running_jobs = set()  # Set of currently running job func-names
        self.server_prog = server_prog
        self.schedule_spec = schedule_spec
        self.conflicts_dict = conflicts_dict    # Dict that identifies functions (jobs) that cannot run in parallel
        self.process_map = process_map      # Dict mapping job (process) name to an executable function
        self.logger = logger
        self.raise_end_schedule = raise_end_schedule
        self.end_if_no_jobs = end_if_no_jobs
        self.sleep_secs = 5 if sleep_secs is None else sleep_secs
        self.defer_end = set_timedelta_from_str_or_int(defer_end) if defer_end else None
        self.new_day_reload = new_day_reload
        self.scheduled_shutdown_times = []      # List of scheduled shutdown times

        self._init_and_report_schedule()


    def _init_and_report_schedule(self):
        """
        Function that initialises the schedule by creating required Jobs records in the database.
        It then reports details of the schedule loaded - writing to logfiles.
        :return:
        """
        # Set jobs that are to run during the day
        self.this_process_job_count, active_job_count, schedule_report = self._init_schedule()
        if schedule_report:
            report = "Scheduled jobs timetable:\n\n" + "\n".join(Job.job_tabular_report_headers[True] + schedule_report) \
                     + f"\n\nSchedule loop sleep time: {self.sleep_secs} sec."
            if active_job_count:
                report += f"\nRunning {self.this_process_job_count} jobs in this process." \
                          + f"\nNote that this process will be {'TERMINATED' if self.end_if_no_jobs else 'RELOADED'} if all jobs become inactive (ended).\n"
                print("==== RUNNING", report)
            else:
                report += f"\n\nWARNING: NO active jobs scheduled for this process.\n"
                print("====", report)
        else:   # No jobs scheduled
            report = "==== NO JOBS SCHEDULED ===="
            print(report)

        if self.logger:
            if schedule_report and active_job_count:
                self.logger.info(report)
            else:  # No jobs or none for this process
                self.logger.info(report, extra={"mail_it": True, "subject": "No active jobs scheduled"})

        if active_job_count == 0:
            raise NoJobsScheduled(f"No jobs scheduled for {self.server_prog}")


    def _init_schedule(self):
        """
        Initialise the schedule using `schedule_spec` (schedule configuration) - results in Job records being created.
        :return: Tuple - (Int: Count of jobs for this process, Int: Count of active jobs for this process, List: Schedule report)
        """
        self.purge_jobs_for_server_prog()
        self.scheduled_shutdown_times = []
        self.set_curr_time()
        this_process_job_count = 0  # Number of jobs for this server
        active_job_count = 0   # Number of jobs for this server that have not ENDED
        schedule_report = []

        # Set jobs that are to run during the day
        for label, start_time_str, frequency, end_time_str, func_name, priority, triggers in self.schedule_spec:
            job = self.add_job(func_name, start_time_str, label=label, priority=priority,
                               periodicity=frequency, end_time=end_time_str, triggers=triggers)
            # Record all scheduled shutdown times
            job_next_start = job.next_start
            if job.func_name == "shutdown" and job_next_start:
                self.scheduled_shutdown_times.append(job_next_start)

            schedule_report.append(job.tabular_format_str(full_date=True))
            if job.func:
                this_process_job_count += 1
                if job.status != ENDED:
                    active_job_count += 1
        # self.log(INFO, f"~~~~~~~ scheduled_shutdown_times: {self.scheduled_shutdown_times}")
        return this_process_job_count, active_job_count, schedule_report

    @classmethod
    def set_curr_time(cls):
        """
        Set the current time
        :return: DateTime object - current time
        """
        cls.current_time = datetime.now(tz=timezone.utc)
        return cls.current_time

    def log(self, level, msg, mail_subject=None):
        if self.logger:
            _extra = {"mail_it": True, "subject": mail_subject} if mail_subject else None
            self.logger.log(level, f"[Schedule {self.server_prog}] " + msg, extra=_extra)
        else:
            print(f"[Schedule {self.server_prog}] Log level {level}: {msg}")

    def _clear_sorted_jobs(self):
        self.sorted_jobs = {V_HIGH: [], HIGH: [], MEDIUM: [], LOW: [], NEVER: []}

    def _add_to_job_list(self, new_job):
        """
        Add new job to the appropriate priority list in the `sorted_jobs` dict.
        :param new_job: Job to add
        :return: Nothing
        """
        job_list = self.sorted_jobs[new_job.priority]
        new_job_next_start = new_job.next_start     # Assign to local variable for efficiency
        if new_job_next_start:
            for ix, job in enumerate(job_list):
                job_next_start = job.next_start
                if job_next_start is None or new_job_next_start < job_next_start:
                    job_list.insert(ix, new_job)    # NB. This is inserting into a list (not the database)
                    return
        job_list.append(new_job)

    def add_job(self, func_name, start_time, func=None, func_args=None, func_kwargs=None,
                label=None, priority=None, periodicity=None, end_time=None, triggers=None, curr_time=None):
        """
        Add a job to the schedule list.  For `func`s that run on the current server a job record will be inserted into
        the database.

        :param func_name: String - Unique name for function to run (ideally <15 characters)
        :param start_time: [OPTIONAL] String - Earliest start time for function in format "HH:MM"
        :param func: [OPTIONAL] Function - Function to execute on the CURRENT server (i.e. the server on which this
                    schedule process is running). If `func` is None, then `func_name` is used to (attempt) to obtain
                    the `func` from the schedule `process_map`.
        :param func_args: [OPTIONAL] List - args to pass to `func` when it executes
        :param func_kwargs: [OPTIONAL] Dict - kwargs to pass to `func` when it executes
        :param label: [OPTIONAL] String - Unique label for particular job (only required if Job may be triggered)
        :param priority: [OPTIONAL] Integer (1 to 4) - Job priority (1: V.High, 2: High, 3: Medium [DEFAULT], 4: Low)
        :param periodicity: [OPTIONAL] Integer or String - Determines job frequency. If None job will be 1-off (unless
                    triggered). Integer value is number of Minutes. String value allow periodicity of hours (e.g. 3h)
                    or minutes (e.g. 15m) or seconds (e.g. 90s)
        :param end_time: [OPTIONAL] String - Latest time that a repeating job can start. In format "HH:MM"
        :param triggers: [OPTIONAL] String or List of Strings - Identifies other Jobs (by their `label`) that should
                    be triggered to run after job completes.  By default, other jobs will only be triggered if the
                    current job `func` returns a value (such as record count or boolean) that evaluates to True. However,
                    by appending "-always" to the label (e.g. "JB1-always") then the job identified by label "JB1" will
                    always be triggered, regardless of value returned by current job `func`
        :param curr_time: [OPTIONAL] - Datetime object - Current time. Will default to Class current_time value.
        :return: Job object
        """
        if func is None:
            func = self.process_map.get(func_name)
        job = Job.init(curr_time or self.current_time,
                       self.server_prog if func else "other",
                       func_name,
                       func,
                       func_args=func_args,
                       func_kwargs=func_kwargs,
                       label=label,
                       priority=priority,
                       start_time=start_time,
                       periodicity=periodicity,
                       end_time=end_time,
                       triggers=triggers,
                       conflicts=self.conflicts_dict.get(func_name)
                       )
        # Only insert job if it runs on this server
        if job.func:
            job.insert()
        self._add_to_job_list(job)  # Done after (optionally) inserting job, so the job record `id` value is set.
        return job

    def sort_jobs(self, priorities_to_sort=None):
        """
        Sort the different priority jobs in ascending order of `next_start` time.  Jobs with `next_start` of None will
        appear at the end.
        :param priorities_to_sort: [OPTIONAL] Set - priorities to sort
        :return:  sorted_jobs dict.
        """
        if priorities_to_sort is None:
            priorities_to_sort = self.priority_order
        for k in priorities_to_sort:
            self.sorted_jobs[k].sort(key=lambda j: (j.next_start or far_future))
        return self.sorted_jobs

    def trigger_job(self, job_label):
        """
        Attempt to trigger the job identified by the supplied job_label.
        :param job_label: String - Label of the job to be triggered.
        :return: Nothing
        """
        # Search through all jobs, looking for one which matches `job_label` parameter
        for k in self.priority_order:
            for job in self.sorted_jobs[k]:
                # If Job with matching label
                if job.label == job_label:
                    # Cannot trigger a job that has ENDED
                    if job.status != ENDED:
                        # If job runs on the current server
                        if job.server_prog == self.server_prog:
                            # Trigger job
                            job.trigger_it(self.current_time)
                            self.log(DEBUG,
                                 f"Triggered job '{job.label} - {job.func_name}', Start-at: {job.next_start}")

                        # Required job runs on another server and a Primer Job does NOT already exist for it
                        elif self.primed_jobs.get(job_label) is None:
                            # Create primer job record (it's creation time will become the required 'next_start' time
                            Job.trigger_remote_job(job_label, self.server_prog, job.func_name)
                            self.log(DEBUG, f"Primer job created for '{job_label}' at {self.current_time}")
                    # Having found job matching the job_label, can exit function
                    return

    def trigger_jobs(self, trigger_list, result_count):
        """
        Trigger any subsequent jobs (identified by their job LABEL) that are dependent on current job finishing. If the
        job label has "-always" appended, then the job will ALWAYS be triggered, otherwise the job will be triggered
        only if the current job returned a result that evaluates to "True" (e.g. it returns a record count > 0 or
        returns a Boolean).

        :param trigger_list: List of job LABEL strings, identifying the job(s) to trigger
        :param result_count: Result of the last run of current job - normally the count of items processed
        :return: Nothing
        """
        if trigger_list:
            self.set_curr_time()     # Set self.current_time
            for _trigger in trigger_list:
                # _trigger will be a job LABEL, optionally with '_always' appended
                job_label, _, when = _trigger.partition('-')
                # if the result evaluates to True or if job should always be triggered
                if result_count or when == "always":
                    # Attempt to trigger the job identified by the job label
                    self.trigger_job(job_label)
        return

    def run_next_pending(self):
        """
        Run the next pending (or triggered) job function.
        :return: None or JobResult object if a job was run
        """
        current_time = self.set_curr_time()
        # Iterate jobs in ascending order of priority, next_start (jobs with no next_start date occur last)
        for k in self.priority_order:
            for job in self.sorted_jobs[k]:
                # ok_to_run has one of 3 values: True, False or None
                ok_to_run = job.can_run(current_time, self.running_jobs)
                if ok_to_run:
                    job_result = job.run(current_time)
                    self.log(DEBUG, f"JOB RESULT - {job_result.describe(exc_name_only=False)}. \nJOB - {str(job)}")
                    self.trigger_jobs(job.triggers, job_result.count)
                    return job_result  # Job run

                # If the job's next_start is in the future or job is waiting for a conflicting job to finish running,
                # we don't need to check any further jobs of this priority
                elif ok_to_run is None:
                    break   # break from inner loop
        return None    # No job run

    def tabular_job_report_list(self, headers=True, separate_priorities=False, full_date=True):
        """
        Return list of jobs, with details of each job presented in tabular (column) format.
        It EXCLUDES the following fields: Last-run, Last-result, Conflicts.

        :param headers: Boolean - True: Include column header & underline rows; False: No headers
        :param separate_priorities: Boolean - True: Insert blank line when priority changes; False: no gap inserted.
        :param full_date: Boolean - True: Show all times as full dates; False: Show just HH:MM or HH:MM:SS.

        :return:  List - empty if NO jobs, otherwise list of strings, possibly including headers.
        """
        job_list = []
        last_len = 0
        for k in self.priority_order:
            if separate_priorities:
                curr_len = len(job_list)
                if curr_len > last_len:
                    job_list.append("")
                    last_len = curr_len
            for job in self.sorted_jobs[k]:
                job_list.append(job.tabular_format_str(full_date))
        if job_list and headers:
            return Job.job_tabular_report_headers[full_date] + job_list
        return job_list

    def displayable_schedule_list(self, full_date=True):
        """
        Return a List of Job formatted data string tuples, from the currently active Schedule
        :param full_date: Boolean - True: full date-time strings are returned; False: shorthand timestrings are returned
        :return: List of Tuples, containing job String values:
        (Label, Server, Func-name, Priority, Status, Earliest, Periodicity, End-time, Next-start, Last-run, Last-results, Triggers, Conflicts)

        """
        job_list = []
        for k in self.priority_order:
            for job in self.sorted_jobs[k]:
                job_list.append(job.formatted_values_tuple(full_date))
        return job_list

    def _init_job_structs_from_database(self):
        """
        Initialise key data structures using Jobs returned by database query.
        :return: Int - Number of jobs being run by current program.
                      IMPORTANT: -1 indicates NO job records exist
        """
        self._clear_sorted_jobs()
        self.running_jobs = set()
        self.primed_jobs = {}  # Primer jobs previously created on this server

        # Retrieved active (not ENDED) jobs from database (in Priority, Next-start ascending order)
        active_jobs = Job.pull_all(pull_name="all_active_sorted")
        if not active_jobs:
            return -1   # Special case - no active jobs in database (all jobs could be ENDED).

        this_process_job_count = 0
        primer_jobs = {}  # Primer jobs created on ANOTHER server
        current_time = self.set_curr_time()
        for job in active_jobs:
            job_priority = job.priority
            # Primer jobs appear first in the list (i.e. their priority is higher than V-HIGH). Primer DICTS:
            #  - `self.primed_jobs` for primer jobs previously created on this server;
            #  - `primer_jobs` for those created on another server
            if job_priority == PRIMER:
                # Primer job previously created on current server
                if job.server_prog == self.server_prog:
                    self.primed_jobs[job.label] = True

                # Else if we haven't already processed primer job with this label. This allows multiple primer
                # jobs for same label to be queued - needed for externally triggered jobs, like adhoc reports.
                elif primer_jobs.get(job.label) is None:
                    # Primer job created on another server, so MAY trigger job on this one
                    primer_jobs[job.label] = job
                continue    # Skip to next job

            ## If we are here, then ALL Primer jobs have been processed
            # Create local variables for efficiency
            job_func_name = job.func_name
            job_runs_on_this_server = job.server_prog == self.server_prog
            append_job = True     # Job is runnable, append job
            if job.status == RUNNING:
                self.running_jobs.add(job_func_name)
            elif job_runs_on_this_server:
                append_job = job.not_too_late(current_time)

            # Job is one that runs on this server
            if job_runs_on_this_server:
                # See if this job has an associated primer job (i.e. current job triggered from another server program)
                primer_job = primer_jobs.pop(job.label, None)

                if append_job:  # Not too late to run the job
                    this_process_job_count += 1
                    job.func = self.process_map.get(job_func_name)
                    # Job needs triggering; if its next_start time changes then will need to insert job in correct place
                    # in sorted jobs list
                    if primer_job:
                        if job.trigger_it(primer_job.created, primer_job.func_args, primer_job.func_kwargs):
                            # Job has been triggered & next-start time has changed, so insert into sorted list
                            self._add_to_job_list(job)
                            append_job = False  # Job has just been added, don't want to add it again below.
                if primer_job:
                    primer_job.delete()  # Delete primer job record from database

            if append_job:
                # Add to sorted_jobs dict of lists (the database query returns jobs in sorted order)
                self.sorted_jobs[job_priority].append(job)

        return this_process_job_count

    def _raise_or_return_on_end_schedule(self, job_flag, msg, log_level=INFO, mail_subj=None):
        """
        It is possible for a schedule to be ended either by Raising an appropriate Base Exception (which will result
        in the application simpling exiting with the exception) OR by returning an equivalent job_flag which will cause
        the schedule process to be exited (returning the job_flag) which can then be handled by the application as
        appropriate.
        :param job_flag: One of END_SCHEDULE, KILL_SCHEDULE, PURGE_SCHEDULE
        :param msg: String - message to Log &, if raising an exception, record as the exception message
        :param log_level: Integer - Log level
        :param mail_subj: String - OPTIONAL "Email subject line" - if an email is to be sent by the logger
        :return:    Either return the job_flag OR RAISE one of 2 base exceptions: PurgeSchedule() or EndSchedule()
        """
        self.log(log_level, msg, mail_subject=mail_subj)
        if self.raise_end_schedule:
            raise JobResult.schedule_end_exception(job_flag, msg)
        else:
            return job_flag

    def _is_likely_scheduled_shutdown(self):
        """
        Establish if job event occurred within 10 minutes of a scheduled shutdown.  The  reason for introducing this
        function was to avoid unnecessary emails being sent related to scheduled shutdowns.

        NB. Reason for function name: ..._likely_...
        1) If database jobs were purged within 10 minutes of a scheduled shutdown (after which applications were
            then restarted, e.g. by the Linux supervisorctl process) then this function would WRONGLY return
            True - expected shutdown.  The likelihood of this occurring is considered low.
        2) If a long-running job was in the process when all database jobs were purged due to a scheduled shutdown,
            then it is possible that this function may be called AFTER the 10-minute window expires - which would
            then WRONGLY result in False being returned (indicating unexpected shutdown). The likelihood of this
            occurring is considered low to medium.
        If wrong result is returned then the impact is LOW as it only affects whether an email is sent when
        the event is logged.

        :return: Boolean - True: Likely due to scheduled shutdown; False: Unlikely to be due to scheduled shutdown
        """
        self.set_curr_time()
        scheduled_shutdown = False
        for shutdown_time in self.scheduled_shutdown_times:
            # self.log(INFO, f"~~~~~~~ shutdown time: {shutdown_time};  current_time: {self.current_time}")
            # If current time is within 10 minutes of a scheduled shutdown (allowing for long running jobs to complete)
            if shutdown_time <= self.current_time <= (shutdown_time + timedelta(minutes=10)):
                scheduled_shutdown = True
                break
        # self.log(INFO, f"~~~~~~~ scheduled_shutdown: {scheduled_shutdown}")
        return scheduled_shutdown

    def run_schedule(self):
        """
        Run the schedule.
        Loops forever, unless Exception raised or an END_SCHEDULE, KILL_SCHEDULE or PURGE_SCHEDULE flag is set.
        :return: JobResult.job_flag - one of END_SCHEDULE, KILL_SCHEDULE, PURGE_SCHEDULE
                or alternatively raises one of: EndSchedule or PurgeSchedule exceptions
        """
        # deferred_end_time: If ending the schedule, this may be set to some time in the future when the schedule
        # is to terminate so that (important) triggered jobs have time to complete.
        deferred_end_time = None
        log_msg = None
        exit_log_level = INFO
        exit_mail_subj = None
        last_date = self.current_time.date()
        try:
            while True:
                sleep(self.sleep_secs)

                # If Not in shut-down phase and just started a new day - then re-initialise schedule
                if self.new_day_reload and deferred_end_time is None and self.set_curr_time().date() > last_date:
                    self._init_and_report_schedule()
                    last_date = self.current_time.date()
                    continue

                # Retrieve jobs from database & populate key dicts (also updates self.current_time)
                this_process_job_count = self._init_job_structs_from_database()
                if deferred_end_time:
                    # if no primer jobs created by this server-prog OR deferred_end_time has been reached
                    if not self.primed_jobs or self.current_time >= deferred_end_time:
                        # End the schedule
                        return self._raise_or_return_on_end_schedule(JobResult.END_SCHEDULE, log_msg, exit_log_level, exit_mail_subj)
                    continue

                if this_process_job_count < 1:    # NO job records in database (may have been purged) or none for this server
                    # Determine if absence of jobs (likely) due to scheduled shutdown
                    unscheduled_shutdown = not self._is_likely_scheduled_shutdown()

                    active_jobs = 0
                    msg = f"No active jobs {'' if this_process_job_count else 'for this process '}in the database."
                    if not self.end_if_no_jobs:     # Attempt to Reload schedule
                        # Re-initialse database & job schedule for this program
                        _, active_jobs, _ = self._init_schedule()
                        self.log(INFO, f"{msg} Schedule RELOADED {'UNEXPECTEDLY ' if unscheduled_shutdown else ''}({active_jobs} jobs active).",
                                 mail_subject="Unexpected job schedule reload" if unscheduled_shutdown else None)

                    if active_jobs == 0:
                        if unscheduled_shutdown:
                            exit_log_level = WARNING
                            exit_mail_subj = "No jobs scheduled - terminating"

                        log_msg = f"{'UNEXPECTEDLY ' if unscheduled_shutdown else ''}ENDING SCHEDULE - {msg}"
                        # If NOT no jobs in database and deferred end required
                        if this_process_job_count != -1 and self.defer_end:
                            deferred_end_time = self.current_time + self.defer_end
                            continue
                        return self._raise_or_return_on_end_schedule(JobResult.END_SCHEDULE, log_msg, exit_log_level, exit_mail_subj)

                # Run next pending job
                job_result = self.run_next_pending()
                if job_result:
                    if job_result.after_run_action_fn:
                        job_result.after_run_action_fn()
                    if job_result.exception:
                        raise job_result.exception
                    end_flag = job_result.end_schedule()
                    if end_flag:
                        # If we get here, job_flag equals END_SCHEDULE, PURGE_SCHEDULE or KILL_SCHEDULE
                        log_msg = f"Schedule {job_result.schedule_end_cause()} job '{job_result.job_name}'."
                        if end_flag == JobResult.END_SCHEDULE and self.defer_end:
                            deferred_end_time = self.current_time + self.defer_end
                        else:
                            return self._raise_or_return_on_end_schedule(job_result.job_flag, log_msg)
        except (SystemExit, KeyboardInterrupt):
            return self._raise_or_return_on_end_schedule(JobResult.KILL_SCHEDULE, f"Schedule KILLED.")
        # Any other exceptions are raised...

    def purge_jobs_for_server_prog(self):
        """
        Delete all jobs for this server prog
        :return: nothing
        """
        Job.delete_jobs_for_server_prog(self.server_prog)

    def purge_all_jobs(self):
        """
        Delete entire schedule from database
        :return:
        """
        Job.purge_all_jobs()
        self.log(INFO, f"All schedule jobs PURGED.")


class Job(dataobj.DataObj, JobDAO):
    """
    Models a job in a schedule that may be executed.  Will have a corresponding Job record in the database `job` table.

    Job properties:
        id - Int - db record id
        created - DateTime - db record created
        label - String - label identifying a job to trigger
        server_prog - String - label identifying Server & Process that created Job record
        func_name - String - Description of function
        func - Executable function
        priority - Int - One of: XXX
        status - Int - One of: XXX
        periodicity - String - Frequency with which job should repeat
        earliest - DateTime - Earliest time the job can start
        end_time - DateTime - Latest time that job can start
        next_start - DateTime - Job next start time
        last_run - DateTime - Time that job was last run
        triggers - List of Strings - Identifies other jobs to trigger when current completes
        conflicts - List of Strings - func_names of other functions that cannot run in parallel with this job
        func_args - List - args to be passed to `func()`
        func_kwargs - Dict - kwargs to be passed to `func()`
    """
    job_tabular_report_headers = {
        False: [
            "Label   Function name     Server prog    Priority   Status     Start  Every    Until  Next      Triggers",
            "------  ----------------  -------------  ---------  ---------  -----  -------  -----  --------  ----------"
        ],
        True: [
            "Label   Function name     Server prog    Priority   Status     Start time           Every    Until time           Next run time        Triggers",
            "------  ----------------  -------------  ---------  ---------  -------------------  -------  -------------------  -------------------  ----------"
        ],
    }
    tabular_field_lengths = {
        False: (8, 18, 15, 11,11, 7, 9, 7, 10, None),
        True: (8, 18, 15, 11, 11, 21, 9, 21, 21, None)
    }

    def __init__(self, *args, func=None, **kwargs):
        """
        Initialisation used when retrieving Job records from database.
        :param args:
        :param func: Function to run
        :param kwargs:
        """
        super().__init__(*args, **kwargs)
        self.func = func

    def __str__(self):
        status = self.status
        return f"Label: {self.label or 'none'};  Function: {self.func_name};  Server: {self.server_prog};  Priority: {priority_str(self.priority)};  Status: {status_str(status, default='None')};  Start: {self._str_or_other(self.earliest, 'unset')};  Every: {self._str_or_other(self.periodicity, 'unset')};  Until: {self._time_or_other(self.end_time, 'unset')};  {'Last start' if status == RUNNING else 'Next start'}: {self._time_or_other(self.next_start, 'unset')};  Last run: {self._time_or_other(self.last_run, 'never')};  Last result: {self._str_or_other(self.last_result, 'none').replace(';', ',')};  Triggers: {self._list_or_other(self.triggers, other='none')};  Conflicts: {self._list_or_other(self.conflicts, other='none')}"

    def __repr__(self):
        return f"{__class__.__name__}( {self.data} )"

    @classmethod
    def init(cls, curr_time, server_prog, func_name, func=None, func_args=None, func_kwargs=None, label=None, priority=None, start_time=None, periodicity=None, end_time=None, triggers=None, conflicts=None):
        """
        Initialise a Job by passing parameters from Schedule specification
        :param curr_time: Datetime Object - Current time
        :param server_prog: String (<= 25 chars) - Identifies server + program that executes the job
        :param func_name: String - Name of function to run
        :param func: The function (executable) to run, should be None if job will run on a different server_prog
        :param func_args: [OPTIONAL] - List of args to pass to `func`
        :param func_kwargs: [OPTIONAL] - Dict of kwargs to pass to `func`
        :param label: [OPTIONAL] String - Unique label for particular job (only required if Job may be triggered)
        :param priority: [OPTIONAL] Integer (1 to 4) - Job priority (1: V.High, 2: High, 3: Medium [DEFAULT], 4: Low)
        :param start_time: Datetime object or String ("HH:MM" format) - Earliest time for job to run (can be None)
        :param periodicity: [OPTIONAL] Integer or String - Determines job frequency. If None job will be 1-off (unless
                    triggered). Integer value is number of Minutes. String value allow periodicity of hours (e.g. 3h)
                    or minutes (e.g. 15m) or seconds (e.g. 90s)
        :param end_time: [OPTIONAL] Datetime object or String (format "HH:MM")- Latest time that a repeating job can start.
        :param triggers: [OPTIONAL] String or List of Strings - Identifies other Jobs (by their `label`) that should
                    be triggered to run after job completes.  By default, other jobs will only be triggered if the
                    current job `func` returns a value (such as record count or boolean) that evaluates to True. However,
                    by appending "-always" to the label (e.g. "JB1-always") then the job identified by label "JB1" will
                    always be triggered, regardless of value returned by current job `func`
        :param conflicts: [OPTIONAL] List of Strings - job functions (identified by `func_name`) that SHOULD NOT run
                    in parallel (simultaneously) with this function.  (If this job is otherwise ready to execute, then
                    execution should wait until NONE of the listed jobs are running).
        :return: Job object
        """
        def _hhmm_str_to_obj(d):
            """
            Convert a time string in format "HH:MM" to a DateTime object.
            :param d: String - Hours/Minutes time in form "HH:MM"
            :return: Datetime object
            """
            if isinstance(d, str):
                # if length of time-string (expected HH:MM) is 4, then assume we have "H:MM", so add a "0" prefix.
                if len(d) == 4:
                    d = "0" + d
                # Create datetime object from current time object (does NOT alter curr_time)
                d = curr_time.replace(hour=int(d[0:2]), minute=int(d[3:5]), second=0, microsecond=0)
            return d

        def _set_next_start(_earliest, _periodicity):
            _next_start = _earliest
            if _periodicity:
                while _next_start <= curr_time:
                    _next_start += _periodicity
            return _next_start

        # CODE #
        if periodicity is not None:
            # periodicity will either be a string like 2h, 10m or an Integer number of MINUTES
            periodicity = set_timedelta_from_str_or_int(periodicity)

        # Adjust earliest & end_time if needed (may need to be changed to tomorrow); set next_start accordingly
        earliest = _hhmm_str_to_obj(start_time)
        end_time = _hhmm_str_to_obj(end_time)
        if earliest and end_time:
            # If earliest is after end, then end must occur tomorrow and earliest some time today
            if earliest > end_time:
                end_time += one_day
                next_start = _set_next_start(earliest, periodicity)
            else:   # earliest <= end_time
                # If end is before now, then set both earliest and end to tomorrow
                if end_time <= curr_time:
                    end_time += one_day
                    earliest += one_day
                    next_start = earliest
                else: # end is later today, next start will be sometime today.
                    next_start = _set_next_start(earliest, periodicity)
        else:
            if earliest:
                # if earliest is before now & cannot be adjusted, set it to tomorrow
                if earliest <= curr_time and not periodicity:
                    earliest += one_day
                next_start = _set_next_start(earliest, periodicity)
            else:
                next_start = None
                # If end is before now, adjust it to tomorrow
                if end_time and end_time <= curr_time:
                    end_time += one_day

        # Set status
        if next_start:
            if end_time and next_start >= end_time:
                next_start = None
                status = ENDED   # Job cannot be run
                priority = NEVER
            elif next_start <= curr_time:
                next_start = None
                status = FINISHED   # Note that a job in this state may still be triggered to run
            else:
                status = PENDING    # Job is ready to run when its next_time is reached (or passed)
        else:
            status = None

        return cls(
            {
            "label": label,
            "server_prog": server_prog,
            "func_name": func_name,
            "priority": priority or MEDIUM,  # set to MEDIUM priority if priority is not set or zero
            "status": status,
            "periodicity": periodicity,
            "earliest": earliest.strftime("%Y-%m-%d %H:%M:%S") if earliest else None, # Save as a formatted string, as don't need to use it again
            "end_time": end_time,
            "next_start": next_start,
            "last_run": None,
            "last_result": None,
            "triggers": None if triggers is None else triggers if isinstance(triggers, list) else [triggers],
            "conflicts": conflicts,
            "func_args": None if func is None else func_args,
            "func_kwargs": None if func is None else func_kwargs
            },
            func=func)

    @property
    def label(self):
        return self._get_single("label")

    # @label.setter
    # def label(self, val):
    #     self._set_single("label", val)

    @property
    def server_prog(self):
        return self._get_single("server_prog")

    # @server_prog.setter
    # def server_prog(self, val):
    #     self._set_single("server_prog", val)

    @property
    def func_name(self):
        return self._get_single("func_name")

    # @func_name.setter
    # def func_name(self, val):
    #     self._set_single("func_name", val)

    @property
    def func_args(self):
        return self._get_single("func_args") or []

    @func_args.setter
    def func_args(self, val):
        self._set_single("func_args", val)

    @property
    def func_kwargs(self):
        return self._get_single("func_kwargs") or {}

    @func_kwargs.setter
    def func_kwargs(self, val):
        self._set_single("func_kwargs", val)

    @property
    def priority(self):
        return self._get_single("priority")

    @priority.setter
    def priority(self, val):
        self._set_single("priority", val, coerce=int)

    @property
    def periodicity(self):
        return self._get_single("periodicity")

    # @periodicity.setter
    # def periodicity(self, val):
    #     self._set_single("periodicity", val)

    @property
    def earliest(self):
        return self._get_single("earliest")

    # @earliest.setter
    # def earliest(self, val):
    #     self._set_single("earliest", val)

    @property
    def end_time(self):
        return self._get_single("end_time")

    # @end_time.setter
    # def end_time(self, val):
    #     self._set_single("end_time", val)

    @property
    def next_start(self):
        return self._get_single("next_start")

    @next_start.setter
    def next_start(self, val):
        self._set_single("next_start", val)

    @property
    def triggers(self):
        return self._get_single("triggers") or []

    # @triggers.setter
    # def triggers(self, val):
    #     self._set_single("triggers", val)

    @property
    def conflicts(self):
        return self._get_single("conflicts") or []

    # @conflicts.setter
    # def conflicts(self, val):
    #     self._set_single("conflicts", val)

    @property
    def last_run(self):
        return self._get_single("last_run")

    @last_run.setter
    def last_run(self, val):
        self._set_single("last_run", val)

    @property
    def last_result(self):
        return self._get_single("last_result")

    @last_result.setter
    def last_result(self, val):
        self._set_single("last_result", val)

    @property
    def status(self):
        return self._get_single("status")

    @status.setter
    def status(self, val):
        self._set_single("status", val)

    @staticmethod
    def _str_or_other(v, other=""):
        return str(v) if v else other

    @staticmethod
    def _time_or_other(d, other="", fmt='%Y-%m-%d %H:%M:%S'):
        # Formats: '%H:%M', '%H:%M:%S', '%Y-%m-%d %H:%M:%S'
        return d.strftime(fmt) if d else other

    @staticmethod
    def _list_or_other(_list, sep=", ", other=""):
        return sep.join(_list) if _list else other

    def formatted_values_tuple(self, full_date=False):
        """
        Return Tuple of values of Job properties in this sequence - all except Integer ID are String values:
        (ID, Label, Func-name, Server, Priority, Status, Earliest, Periodicity, End-time, Last-run, Next-start, Triggers)

        :param full_date: Boolean - True: Show full date/time; False - Show abbreviated time (no date component)
        :return: Tuple of Strings (except for ID) -
            (integer-ID, Label, Func-name, Server, Priority, Status, Earliest, Periodicity, End-time, Next-start, Last-run, Last-result, Triggers, Conflicts)

        """
        earliest = self.earliest or ""
        if earliest and not full_date:
            earliest = earliest[11:16]  # YYYY-MM-DD HH:MM:SS  -->  HH:MM
        if full_date:
            fmt_hms = fmt_hm = "%Y-%m-%d %H:%M:%S"
        else:
            fmt_hms = "%H:%M:%S"
            fmt_hm = "%H:%M"

        return (
                self.id,
                self.label or "",
                self.func_name,
                self.server_prog or "",
                priority_str(self.priority),
                status_str(self.status),
                earliest,
                self._str_or_other(self.periodicity),
                self._time_or_other(self.end_time, fmt=fmt_hm),
                self._time_or_other(self.next_start, fmt=fmt_hms),
                self._time_or_other(self.last_run, fmt=fmt_hms),
                self._str_or_other(self.last_result),
                self._list_or_other(self.triggers),
                self._list_or_other(self.conflicts)
            )

    def tabular_format_str(self, full_date=True):
        """
        Return a string of Job properties formatted for tabular display
        :param full_date: Boolean - True: Datetime properties will include BOTH date & time: YYYY-MM-DD HH:MM:SS
                                    False: Datetime properties  will contain only the Time component: HH:MM:SS
        :return: String of following Job properties:
                Label, Func-name, Server, Priority, Status, Earliest, Periodicity, End-time, Last-run, Next-start, Triggers
        """
        # Lengths of fields in following order: Label, Func-name, Server, Priority, Status, Earliest, Periodicity, End-time, Next-start, Triggers
        field_lengths = self.tabular_field_lengths[full_date]
        str_vals = self.formatted_values_tuple(full_date)
        s = ""
        # Loop over all values except first: ID and last 4:  Last-run, Last-result, Triggers, Conflicts
        for x, v in enumerate(str_vals[1:-4]):
            s += v.ljust(field_lengths[x])
        s += str_vals[-2]   # Triggers has no fixed length
        # We discard these elements from str_vals: ID, Last-run, Last-results & Conflicts
        return s

    @classmethod
    def trigger_remote_job(cls, job_label, server_prog, func_name, func_args=None, func_kwargs=None):
        """
        Trigger a job, identified by `job_label` parameter, on another server or program.  This function creates a
        primer job in the database.

        :param job_label: String - Label of the remote job that is to be triggered
        :param server_prog: String - "Server.Program" of current program
        :param func_name: String - Name of function (job) being triggered
        :param func_args: List - [OPTIONAL] Args to be passed to triggerd job
        :param func_kwargs: Dict - [OPTIONAL] Kwargs to be passed to triggerd job
        :return: Nothing
        """
        # Create primer job record (it's creation time will become the required 'next_start' time
        cls({
            "label": job_label,
            "server_prog": server_prog,
            "func_name": f"TRIGGER_{func_name}",
            "priority": PRIMER,
            "status": None,
            "func_args": func_args,
            "func_kwargs": func_kwargs
        }).insert()

    def _set_ended_values(self):
        self.status = ENDED
        self.priority = NEVER  # Will prevent job being retrieved from database in future
        self.next_start = None

    def not_too_late(self, check_time, do_update=True):
        """
        Check whether it is too late to run the job (i.e. current time exceeds job end-time), if so update the job's
        status & priority.
        :param check_time: Datetime object - time to compare end time against (typically the current time).
        :param do_update: Boolean - True: Update the Job record; False: do NOT update Job record
        :return: Boolean - True: Not too late to run job; False - job end-time has been reached (cannot run job).
        """
        end_time = self.end_time    # assign to local variable for efficiency
        if end_time and check_time > end_time:
            # Too late
            self._set_ended_values()
            if do_update:
                self.update()
            return False
        else:
            return True

    def _any_running_job_conflict(self, running_jobs):
        """
        Check whether current job conflicts with any running jobs.  If so, then the current job must wait until conflicting
        job is no longer running.
        :param running_jobs: Set of `func_name`s of Jobs currently running
        :return: String - Name of conflicting job or None
        """
        for func_name in self.conflicts:
            if func_name in running_jobs:
                # If Job status NOT already WAITING, update it to WAITING
                if self.status != WAITING:
                    self.status = WAITING
                    self.update()
                return func_name    # Name of conflicting job that is running
        return None     # No conflicting jobs

    def can_run(self, curr_time, running_jobs):
        """
        Check if a job is OK to run.
        :param curr_time: Datetime object - Current time (i.e. "now")
        :param running_jobs: Set of `func_name`s of Jobs currently running
        :return: 1 of 3 values:
                    None: Job must wait for conflicting running job to finish or Job next start is in the future;
                    True: Job can run;
                    False: Job not runnable.
        """
        status = self.status  # assign to local variable for efficiency
        if status:
            next_start = self.next_start    # assign to local variable for efficiency
            if next_start:
                if next_start > curr_time:      # next_start is in the future
                    return None     # Job must wait until next start time is reached

                if self.func:
                    if status in (TRIGGERED, PENDING, WAITING):
                        if self.not_too_late(curr_time):
                            if self._any_running_job_conflict(running_jobs):
                                return None     # Job must wait until conflicting job finishes
                            else:
                                return True     # Job can run
        return False    # Job not runnable

    def trigger_it(self, start_at=None, func_args=None, func_kwargs=None):
        """
        Trigger the current job: change its status to TRIGGERED.  Possibly also change the `job_next_start` time, if it
        is None or later than the `start_at` time.
        :param start_at: Datetime object - Time when job should be run (defaults to now())
        :param func_args: List - Args to be passed to func
        :param func_kwargs: Dict - Keyword Args to be passed to func
        :return: Boolean - True: `job_next_start` was changed (indicating that re-sorting required) or
                           False: `job_next_start` unchanged (indicating re-sorting not needed).
        """
        if start_at is None:
            start_at = datetime.now(tz=timezone.utc)
        next_start_changed = False
        self.status = TRIGGERED
        job_next_start = self.next_start
        # Only set next_start if not set, or it is later than start_at
        if job_next_start is None or job_next_start > start_at:
            self.next_start = start_at
            next_start_changed = True
        if func_args:
            self.func_args = func_args
        if func_kwargs:
            self.func_kwargs = func_kwargs
        self.update()
        return next_start_changed

    def run(self, run_time):
        """
        Execute the job function `func`, which will typically return either a JobResult object or an integer count of
        items processed (but could be something else).

        This function also updates values: next_start, status, and possibly priority (if ENDED) and updates the job
        record.  The `next_start` will be set to a future time by applying periodicity (if set) to the run_time
        (as long as it doesn't then exceed end_time), otherwise None.

        IMPORTANT: This function is normally called by Schedule.run_next_pending(), within Schedule.run_schedule() and
        WILL only be called if priority isn't NEVER and status is one of WAITING, PENDING, TRIGGERED and not too late
        to run job; hence these aspects are NOT tested within this function.

        :param run_time: DateTime - time that the job is run
        :return: JobResult object
        """
        try:
            self.status = RUNNING
            self.last_run = run_time
            self.update()  # Update db record
            # Run the function
            job_result = self.func(*self.func_args, **self.func_kwargs)
            if isinstance(job_result, JobResult):
                if not job_result.job_name:
                    job_result.job_name = self.func_name
            else:   # job_result is expected to hold the number of items processed (i.e. COUNT)
                job_result = JobResult(self.func_name, job_result)
        except (SystemExit, KeyboardInterrupt):
            job_result = JobResult(self.func_name, job_flag=JobResult.KILL_SCHEDULE)
        except Exception as e:
            job_result = JobResult(self.func_name, exception=e)
        finally:    # ALWAYS execute the following logic, even if exception arises.
            if job_result.job_flag == JobResult.END_JOB:
                self._set_ended_values()
            else:
                periodicity = self.periodicity  # assign to local variable for efficiency
                # Set next run time if required
                if periodicity:
                    curr_time = Schedule.set_curr_time()  # Update current time, as job may have taken significant time to run
                    while run_time <= curr_time:
                        run_time += periodicity
                    # If too late, then `not_too_late(...)` updates next_start, status & priority values
                    if self.not_too_late(run_time, do_update=False):
                        self.next_start = run_time
                        self.status = PENDING
                else:
                    self.next_start = None
                    self.status = FINISHED
            # Stringified job result - possibly containing Count; Result; Flag; Exception
            self.last_result = job_result.describe("CRFE")
            self.update()   # Update db record
        return job_result


    @classmethod
    def delete_jobs_for_server_prog(cls, server_prog):
        """
        Delete jobs for specified server & program.
        :param server_prog:
        :return: Nothing
        """
        cls.delete_by_query(server_prog, del_name="all_4_server_prog")


    @classmethod
    def purge_all_jobs(cls):
        """
        Remove all job records (for ALL servers) - also has the effect of resetting the next primary key `id` to 1.
        :return: Nothing
        """
        cls.truncate_table()


def displayable_schedule_list_from_config(schedule_config, conflicts_dict, full_date=True):
    """
    Returns a list of Job formatted data string tuples derived from the `schedule_spec_list`
    :param schedule_config: List of tuples that define the required Schedule - config values
    :param conflicts_dict: Dict that identifies functions (jobs) that cannot run in parallel - config values
    :param full_date: Boolean - True: full date-time strings are returned; False: shorthand timestrings are returned
    :return: List of Tuples, containing job String values:
    (Label, Server, Func-name, Priority, Status, Earliest, Periodicity, End-time, Next-start, Last-run, Last-results, Triggers, Conflicts)
    """
    curr_time = datetime.now(tz=timezone.utc)
    return [
        Job.init(curr_time,
                 "",
                 func_name,
                 label=label,
                 priority=priority,
                 start_time=start_time_str,
                 periodicity=mins_interval,
                 end_time=end_time_str,
                 triggers=triggers,
                 conflicts=conflicts_dict.get(func_name)
                 ).formatted_values_tuple(full_date)
        for label, start_time_str, mins_interval, end_time_str, func_name, priority, triggers in schedule_config
    ]


def displayable_schedule_list_from_db(sort_priority=True, full_date=True):
    """
    Returns a list of Job formatted data string tuples derived from the `schedule_spec_list`
    :param sort_priority: Boolean - True: Jobs sorted by priority then next-start; False: Jobs sorted by next-start, then priority
    :param full_date: Boolean - True: full date-time strings are returned; False: shorthand time strings are returned

    :return: List of Tuples, containing job String values (except for Int ID):
        (Int-ID, Label, Server, Func-name, Priority, Status, Earliest, Periodicity, End-time, Next-start, Last-run, Last-results, Triggers, Conflicts)

    """
    return [job.formatted_values_tuple(full_date)
            for job in Job.pull_all(pull_name="all_sorted_priority" if sort_priority else "all_sorted_nextstart")]

