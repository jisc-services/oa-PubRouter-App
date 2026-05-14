"""
Unit tests for the schedule.py library
"""
from datetime import datetime, timezone, timedelta
from dateutil.relativedelta import relativedelta
from logging import INFO

from flask import current_app

from octopus.modules.logger.test_helper import LoggingBufferContext
from tests.fixtures.testcase import JPERMySQLTestCase

from router.shared.models.schedule import TRIGGERED, PENDING, WAITING, RUNNING, FINISHED, ENDED, PRIMER, V_HIGH, HIGH, \
           MEDIUM, LOW, NEVER, NoJobsScheduled, JobResult, Schedule, Job, set_timedelta_from_str_or_int
from router.jper.app import app_decorator


class TestSchedule(JPERMySQLTestCase):
    # Dict that PREVENTS key processes from running in parallel (simultaneously)
    scheduler_conflicts = {
        # 'key-function-name': ['list-of-functions-that-CANNOT-run-at-the-same-time-as-key-function', ...]
        # "aaa": [""],
        "bbb": ["ccc", "ddd", "eee"],
        "ccc": ["bbb", "ddd", "eee"],
        "ddd": ["bbb", "ccc", "eee"],
        "eee": ["bbb", "ccc", "ddd"]
    }

    func_return_values = None
    def set_func_return_values(self, func_name, count, str_1, flag, after_run_action_fn, exc):
        self.func_return_values[func_name] = [func_name, count, str_1, flag, after_run_action_fn, exc]

    @staticmethod
    def ret_job_result(func_name, int_num, str_1, flag, after_run_action_fn, exc):
        job_result = JobResult(count=int_num, func_return=(int_num, str_1), job_flag=flag)
        if exc:
            job_result.exception = exc(f"Raised by {func_name}...")
        if after_run_action_fn:
            job_result.after_run_action_fn = after_run_action_fn
        return job_result

    def aaa(self):
        (func_name, count, str_1, flag, after_run_action_fn, exc) = self.func_return_values["aaa"]
        if exc:
            raise exc("aaa")
        return count

    def bbb(self):
        return self.ret_job_result(* self.func_return_values["bbb"])

    def ccc(self):
        return self.ret_job_result(* self.func_return_values["ccc"])

    def ddd(self):
        return self.ret_job_result(* self.func_return_values["ddd"])

    def eee(self):
        return self.ret_job_result(* self.func_return_values["eee"])

    @staticmethod
    def shutdown():
        return JobResult(job_flag=JobResult.PURGE_SCHEDULE)


    @classmethod
    @app_decorator
    def setUpClass(cls):
        """
        Create JPER test database `job` table.  NB. The database is created by TestMySQL.setUpClass().
        """
        cls.tables_for_testing = ['job']

        super(TestSchedule, cls).setUpClass()

        cls.current_test_time = datetime.now(tz=timezone.utc)   # Current time
        cls.today = cls.current_test_time.replace(hour=0, minute=0, second=0, microsecond=0)
        cls.tomorrow = cls.today + relativedelta(days=1)
        current_app.logger.setLevel(INFO)
        
    def setUp(self):
        super(TestSchedule, self).setUp()
        self.func_return_values = {
            # func-name: (count, str_1, flag, after-run-fn, exception)
            "aaa": ("aaa", 0, None, None, None, None),
            "bbb": ("bbb", 0, None, None, None, None),
            "ccc": ("ccc", 0, None, None, None, None),
            "ddd": ("ddd", 0, None, None, None, None),
            "eee": ("eee", 0, None, None, None, None),
        }

    def tearDown(self):
        print("\n-- DIAGNOSTICS BEFORE closing all connections",  Job.diagnostics_str(), "\n")
        Job.close_all_connections()
        super(TestSchedule, self).tearDown()

    @classmethod
    def return_particular_time(cls):
        return cls.current_test_time

    @classmethod
    def calc_today_time(cls, hh_mm_str):
        return cls.today.replace(hour=int(hh_mm_str[0:2]), minute=int(hh_mm_str[3:5]), second=0, microsecond=0)

    @classmethod
    def set_test_curr_time(cls, hh_mm_str):
        """
        Force the Schedule set_curr_time function to return a particular time as a  datetime object
        :return: DateTime object - current time
        """
        cls.current_test_time = cls.calc_today_time(hh_mm_str)
        Schedule.current_time = cls.current_test_time
        Schedule.set_curr_time = cls.return_particular_time
        return cls.current_test_time

    @app_decorator
    def test_01_schedule_initialisation_and_purging(self):
        """
        Check that schedule initialises as expected - the calculated Job Start-time, End-time, Next-start and Status
        are all critically depend on the effective time that Initialisation takes place.

        General initialisation rules:
            If configured Start > End, then End-time will always be the next day.

            If Start < End, and both are earlier than the Schedule initialisation time, again both will be set to the
            next day.

            If Start < End, and Schedule is initialised between Start & End time, and there is a repeat periodicity then
            Next start will be calculated by adding periodicity repeatedly to the start time until it exceeds
            initialisation time.

            If Start < End, and Schedule is initialised between Start & End time, but there is NO repeat periodicity
            then Next start will not be set, & status will be Finished because the start time has passed.

        Purging: Check that the 2 purge functions work as expected.

        IMPORTANT: This test simulates 2 servers, by initialising 2 schedules (using the same config),
        with different Server-Prog values & using different Process-maps.
        """
        proc_map_1 = {
            'aaa': self.aaa,
            'bbb': self.bbb,
            }

        proc_map_2 = {
            'ccc': self.ccc,
            'ddd': self.ddd,
            'eee': self.eee
            }

        # This test schedule is designed for use with an effective Schedule INITIALISATION TIME of 13:00 (set below)
        test_schedule_spec = [
            # ("Label (unique)", "start-time", interval: mins-integer or string like '10s', '20m' or '3h', "end-time", "process-name", priority-int 1 to 4, "trigger" string or list of strings)
            # If there is no interval then assumed to be a one off event

            # LABEL code: ..SxFxz --> Start & Finish day, where S1/F1: start/finish today, S2/F2: start/finish tomorrow, z --> Status indicator
            # V-High status, all with Start time > End time, Func name "aaa"
            ("vaS1F2p", "11:00", 30, "10:00", "aaa", 1, "T1"),   # Start > End, 30min repeat --> Expect Start TODAY, End-time to be TOMORROW and Next-start to be 13:30, PENDING
            ("vbS1F2p", "14:00", 60, "10:00", "aaa", 1, "T2"),   # Start > End, 60min repeat --> Expect Start TODAY, End-time to be TOMORROW and Next-start to be 14:00, PENDING
            ("vcS0F2f", "11:00", None, "10:30", "aaa", 1, "T3-always"), # Start > End, no repeat --> Expect Start TODAY, End-time TOMORROW, NO Next-start, FINISHED
            ("vdS1F2p", "14:15", None, "10:45", "aaa", 1, "T4"), # Start > End, no repeat --> Expect Start TODAY, End-time TOMORROW, Next-start 14:15, PENDING

            # High status, all with Start time < End time, Func name "bbb"
            ("haS2F2p", "08:30", 60, "11:00", "bbb", 2, None),   # Start < End, 60m repeat --> Expect Start & End times TOMORROW, Next-start 08:30 tomorrow, PENDING
            ("hbS1F1p", "09:00", 30, "14:30", "bbb", 2, None),   # Start < End, 30m repeat --> Expect Start & End times TODAY, Next-start 13:30, PENDING
            ("hcS1F1f", "08:00", 300, "15:00", "bbb", 2, None),  # Start < End, 5h repeat --> Expect Start & End times TODAY, NO Next-start, ENDED
            ("hdS2F2p", "09:15", None, "11:15", "bbb", 2, None), # Start < End, no repeat --> Expect Start & End times TOMORROW, Next-start 9:15 tomorrow, PENDING
            ("heS1F1f", "10:00", None, "14:00", "bbb", 2, None), # Start < End, no repeat --> Expect Start & End times TODAY, NO Next-start, FINISHED

            # Medium status, all with Start time, NO End time, Func name "ccc"
            ("maS1F-p", "11:11", 60, None, "ccc", 3, None),       # Start, 60m repeat --> Start TODAY, Next start 13:11, PENDING
            ("mbS2F-p", "11:20", None, None, "ccc", 3, None),     # Start, no repeat --> Start TOMORROW, Next start 11:20 tomorrow, PENDING
            ("mcS1F-p", "16:00", 60, None, "ccc", None, None),    # Start, 60m repeat --> Start TODAY, Next start 16:00, PENDING
            ("mdS1F-p", "15:00", None, None, "ccc", None, None),   # Start, No repeat --> Start TODAY, Next start 15:00, PENDING

            # Low status, all with NO Start time, Func name "ddd"
            ("laS-F2", None, 60, "11:00", "ddd", 4, ["D1", "D2"]),      # Finish, 60m repeat --> NO Start, Finish TOMORROW, NO status
            ("lbS-F2", None, None, "12:00", "ddd", 4, ["D1", "D2"]),    # Finish, no repeat --> NO Start, Finish TOMORROW, NO status
            ("lcS-F1", None, 60, "15:00", "ddd", 4, ["D1", "D2"]),      # Finish, no repeat --> NO Start, Finish TODAY, NO status
            ("ldS-F1", None, None, "15:00", "ddd", 4, ["D1", "D2"]),    # Finish, no repeat --> NO Start, Finish TODAY, NO status

            # Medium status, Function Name 'xxx' NOT in `cls.proc_map` so NO Job records will be created
            ("moaS1F-p", "16:00", 60, None, "xxx", None, None),  # Start, 60m repeat --> Start TODAY, Next start 16:00, PENDING
            ("mobS1F-p", "15:15", None, None, "xxx", None, None),  # Start, No repeat --> Start TODAY, Next start 15:15, PENDING
        ]
        # Spoof current time to be 13:00
        self.set_test_curr_time("13:00")
        schedule_curr_time = Schedule.set_curr_time()
        assert schedule_curr_time == self.current_test_time

        scheduler_1 = Schedule("App1", "Prog1", test_schedule_spec, self.scheduler_conflicts, proc_map_1)
        scheduler_2 = Schedule("App2", "Prog2", test_schedule_spec, self.scheduler_conflicts, proc_map_2)

        # Create Dict, keyed by Job label, of ALL MEDIUM priority jobs set from Schedule config for scheduler-1
        med_sched_job_dict_1 = {job.label: job for job in scheduler_1.sorted_jobs[MEDIUM]}
        assert len(med_sched_job_dict_1) == 6    # There are 6 Medium priority jobs in the configuration

        # Create Dict, keyed by Job label, of ALL MEDIUM priority jobs set from Schedule config for scheduler-1
        med_sched_job_dict_2 = {job.label: job for job in scheduler_2.sorted_jobs[MEDIUM]}
        assert len(med_sched_job_dict_2) == 6    # There are 6 Medium priority jobs in the configuration

        # Retrieve all Job records from database, sorted by Priority, Next-start time
        job_recs = Job.pull_all(pull_name="all_sorted_priority")
        assert len(job_recs) == 17  # Expect 17 job records
        # Create Dict, keyed by Job label of all jobs in database
        db_job_dict = {job.label: job for job in job_recs}

        # Confirm that jobs with Func-names "xxx" exist for both schedulers
        for med_sched_job_dict in (med_sched_job_dict_1, med_sched_job_dict_2):
            for other_jobs in ("moaS1F-p", "mobS1F-p"):
                med_sched_job = med_sched_job_dict[other_jobs]
                assert med_sched_job.func_name == "xxx"
                assert med_sched_job.server_prog == "other"
                assert med_sched_job.priority == MEDIUM
                assert med_sched_job.status == PENDING
                assert db_job_dict.get(other_jobs) is None      # Other jobs NOT created in database

        # Confirm that for Schedule 1, all jobs that DON'T appear in proc_map_1, have server_prog of "other"
        for k in Schedule.priority_order:
            for job in scheduler_1.sorted_jobs[k]:
                assert job.server_prog == "App1.Prog1" if job.func_name in proc_map_1 else "other"

        # Confirm that for Schedule 2, all jobs that DON'T appear in proc_map_2, have server_prog of "other"
        for k in Schedule.priority_order:
            for job in scheduler_2.sorted_jobs[k]:
                assert job.server_prog == "App2.Prog2" if job.func_name in proc_map_2 else "other"

        # These are the initial properties expected for each initialised job
        # Each tuple in the list contains:
        # (label, f_name, server_prog, priority, status, period, earliest, end_time, next_start, triggers, conflicts)
        expected_results = [
            ("vaS1F2p", "aaa", "App1.Prog1", V_HIGH, PENDING,
             timedelta(minutes=30),  # period
             (self.today.replace(hour=11, minute=0)).strftime("%Y-%m-%d %H:%M:%S"),  # earliest
             self.tomorrow.replace(hour=10, minute=0),  # end
             self.today.replace(hour=13, minute=30),  # next start
             ["T1"], []
             ),

            ("vbS1F2p", "aaa", "App1.Prog1", V_HIGH, PENDING,
             timedelta(minutes=60),  # period
             (self.today.replace(hour=14, minute=0)).strftime("%Y-%m-%d %H:%M:%S"),  # earliest
             self.tomorrow.replace(hour=10, minute=0),  # end
             self.today.replace(hour=14, minute=0),  # next start
             ["T2"], []
             ),

            ("vcS0F2f", "aaa", "App1.Prog1", V_HIGH, FINISHED,
             None,  # period
             (self.today.replace(hour=11, minute=0)).strftime("%Y-%m-%d %H:%M:%S"),  # earliest
             self.tomorrow.replace(hour=10, minute=30),  # end
             None,  # next start
             ["T3-always"], []
             ),

            ("vdS1F2p", "aaa", "App1.Prog1", V_HIGH, PENDING,
             None,  # period
             (self.today.replace(hour=14, minute=15)).strftime("%Y-%m-%d %H:%M:%S"),  # earliest
             self.tomorrow.replace(hour=10, minute=45),  # end
             self.today.replace(hour=14, minute=15),  # next start
             ["T4"], []
             ),

            ("haS2F2p", "bbb", "App1.Prog1", HIGH, PENDING,
             timedelta(minutes=60),  # period
             (self.tomorrow.replace(hour=8, minute=30)).strftime("%Y-%m-%d %H:%M:%S"),  # earliest
             self.tomorrow.replace(hour=11, minute=0),  # end
             self.tomorrow.replace(hour=8, minute=30),  # next start
             [], ["ccc", "ddd", "eee"]
             ),

            ("hbS1F1p", "bbb", "App1.Prog1", HIGH, PENDING,
             timedelta(minutes=30),  # period
             (self.today.replace(hour=9, minute=0)).strftime("%Y-%m-%d %H:%M:%S"),  # earliest
             self.today.replace(hour=14, minute=30),  # end
             self.today.replace(hour=13, minute=30),  # next start
             [], ["ccc", "ddd", "eee"]
             ),

            ("hcS1F1f", "bbb", "App1.Prog1", NEVER, ENDED,
             timedelta(minutes=300),  # period
             (self.today.replace(hour=8, minute=0)).strftime("%Y-%m-%d %H:%M:%S"),  # earliest
             self.today.replace(hour=15, minute=0),  # end
             None,  # next start
             [], ["ccc", "ddd", "eee"]
             ),

            ("hdS2F2p", "bbb", "App1.Prog1", HIGH, PENDING,
             None,  # period
             (self.tomorrow.replace(hour=9, minute=15)).strftime("%Y-%m-%d %H:%M:%S"),  # earliest
             self.tomorrow.replace(hour=11, minute=15),  # end
             self.tomorrow.replace(hour=9, minute=15),  # next start
             [], ["ccc", "ddd", "eee"]
             ),

            ("heS1F1f", "bbb", "App1.Prog1", HIGH, FINISHED,
             None,  # period
             (self.today.replace(hour=10, minute=0)).strftime("%Y-%m-%d %H:%M:%S"),  # earliest
             self.today.replace(hour=14, minute=0),  # end
             None,  # next start
             [], ["ccc", "ddd", "eee"]
             ),

            ("maS1F-p", "ccc", "App2.Prog2", MEDIUM, PENDING,
             timedelta(minutes=60),  # period
             (self.today.replace(hour=11, minute=11)).strftime("%Y-%m-%d %H:%M:%S"),  # earliest
             None,  # end
             self.today.replace(hour=13, minute=11),  # next start
             [], ["bbb", "ddd", "eee"]
             ),

            ("mbS2F-p", "ccc", "App2.Prog2", MEDIUM, PENDING,
             None,  # period
             (self.tomorrow.replace(hour=11, minute=20)).strftime("%Y-%m-%d %H:%M:%S"),  # earliest
             None,  # end
             self.tomorrow.replace(hour=11, minute=20),  # next start
             [], ["bbb", "ddd", "eee"]
             ),

            ("mcS1F-p", "ccc", "App2.Prog2", MEDIUM, PENDING,
             timedelta(minutes=60),  # period
             (self.today.replace(hour=16, minute=0)).strftime("%Y-%m-%d %H:%M:%S"),  # earliest
             None,  # end
             self.today.replace(hour=16, minute=0),  # next start
             [], ["bbb", "ddd", "eee"]
             ),

            ("mdS1F-p", "ccc", "App2.Prog2", MEDIUM, PENDING,
             None,  # period
             (self.today.replace(hour=15, minute=0)).strftime("%Y-%m-%d %H:%M:%S"),  # earliest
             None,  # end
             self.today.replace(hour=15, minute=0),  # next start
             [], ["bbb", "ddd", "eee"]
             ),

            ("laS-F2", "ddd", "App2.Prog2", LOW, None,
             timedelta(minutes=60),  # period
             None,  # earliest
             self.tomorrow.replace(hour=11, minute=0),  # end
             None,  # next start
             ["D1", "D2"], ["bbb", "ccc", "eee"]
             ),

            ("lbS-F2", "ddd", "App2.Prog2", LOW, None,
             None,  # period
             None,  # earliest
             self.tomorrow.replace(hour=12, minute=0),  # end
             None,  # next start
             ["D1", "D2"], ["bbb", "ccc", "eee"]
             ),

            ("lcS-F1", "ddd", "App2.Prog2", LOW, None,
             timedelta(minutes=60),  # period
             None,  # earliest
             self.today.replace(hour=15, minute=0),  # end
             None,  # next start
             ["D1", "D2"], ["bbb", "ccc", "eee"]
             ),

            ("ldS-F1", "ddd", "App2.Prog2", LOW, None,
             None,  # period
             None,  # earliest
             self.today.replace(hour=15, minute=0),  # end
             None,  # next start
             ["D1", "D2"], ["bbb", "ccc", "eee"]
             ),
        ]

        assert len(db_job_dict) == len(expected_results)

        for label, f_name, server_prog, priority, status, period, earliest, end_time, next_start, triggers, conflicts in expected_results:
            # Retrieve each Job & confirm it has been initialised as expected
            job = db_job_dict[label]
            assert job.func_name == f_name
            assert job.server_prog == server_prog
            assert job.priority == priority
            assert job.status == status
            assert job.periodicity == period
            assert job.earliest == earliest
            assert job.end_time == end_time
            assert job.next_start == next_start
            assert job.triggers == triggers
            assert job.conflicts == conflicts

        # Check that the ENDED job is NOT returned by the "all_active_sorted" query
        active_job_recs = Job.pull_all(pull_name="all_active_sorted")
        assert len(active_job_recs) == 16  # One of the 17 jobs has ENDED & so has priority NEVER

        # Check that jobs for specified server-prog are purged
        scheduler_1.purge_jobs_for_server_prog()
        db_jobs_after_purging = Job.pull_all(pull_name="all_sorted_priority")
        # Only the scheduler_2 jobs should remain in database
        assert len(db_jobs_after_purging) == 8
        for job in db_jobs_after_purging:
            assert job.server_prog == scheduler_2.server_prog

        # Check that purge all jobs works
        scheduler_1.purge_all_jobs()
        db_jobs_after_purging = Job.pull_all(pull_name="all_sorted_priority")
        # No jobs should remain
        assert len(db_jobs_after_purging) == 0
        # print(displayable_schedule_list_from_db())

    @app_decorator
    def test_02_job_methods(self):
        """
        Check that various Job methods operate as expected:
            * set_timedelta_from_str_or_int()
            * init()
            * formatted_values_tuple()
            * not_too_late()
            * can_run()
            * run()
            * trigger_it()
            * trigger_remote_job()
            * purge_all_jobs()
        :return:
        """
        ## 1 ## `set_timedelta_from_str_or_int()`
        ok_frequency_values = [
            (20, timedelta(minutes=20)),
            ("30s", timedelta(seconds=30)),
            ("300 s", timedelta(seconds=300)),
            ("10m", timedelta(minutes=10)),
            ("15h", timedelta(hours=15)),
        ]
        for test_val, expected_result in ok_frequency_values:
            assert set_timedelta_from_str_or_int(test_val) == expected_result

        bad_frequency_values = [
            "20",
            "40x",
            "40ss",
        ]
        for test_val in bad_frequency_values:
            with self.assertRaises(ValueError):
                set_timedelta_from_str_or_int(test_val)

        ## 2 ## Job `init()` - partial test, fully tested via `test_01_schedule_initialisation_and_purging` above.
        curr_time = self.set_test_curr_time("11:00")

        def func_2_run(a, b, x=None):
            """
            Function being run by job.
            """
            if a is None or b is None or x is None:
                raise ValueError("BAD PARAM VALUES")
            ret_val = 0
            if a == x.get("a"):
                ret_val += 1
            if b == x.get("b"):
                ret_val += 10
            return ret_val

        job = Job.init(curr_time,
                       "Test.Prog",
                       "func_2_run",
                       func=func_2_run,
                       func_args=["AA", "BB"],          # Values are used within `func_2_run` for testing
                       func_kwargs={"x": {"a": "AA", "b": "BB"}},   # Values are used within `func_2_run` for testing
                       label="B1",
                       priority=LOW,
                       start_time="10:00",
                       periodicity=15,
                       end_time="17:00",
                       triggers=["L2", "L3"],
                       conflicts=["func_2", "func_3"]
                       )
        job.insert()


        ## 3 ## `formatted_values_tuple()`
        job_vals = job.formatted_values_tuple(True)
        # job_vals tuple:
        # Label, Func-name, Server, Priority, Status, Earliest, Periodicity, End-time, Last-run, Next-start, Triggers, Conflicts
        assert job_vals == (
            job.id,
            'B1',
            'func_2_run',
            'Test.Prog',
            'Low',
            'Pending',
            self.calc_today_time("10:00").strftime("%Y-%m-%d %H:%M:%S"),  # Start
            '0:15:00',
            self.calc_today_time("17:00").strftime("%Y-%m-%d %H:%M:%S"),  # End
            # Next start (earliest time after the current time, that is multiple of frequency)
            self.calc_today_time("11:15").strftime("%Y-%m-%d %H:%M:%S"),
            '',     # Last start
            '',     # Last results
            'L2, L3',
            'func_2, func_3'    # Conflicts
        )

        job_vals = job.formatted_values_tuple(False)
        assert job_vals == (
            job.id,
            'B1',
            'func_2_run',
            'Test.Prog',
            'Low',
            'Pending',
            '10:00',    # Start
            '0:15:00',  # Frequency
            '17:00',    # End
            '11:15:00', # Next start (earliest time after the current time, that is multiple of frequency)
            '',     # Last start
            '',     # Last results
            'L2, L3',
            'func_2, func_3'    # Conflicts
        )


        ## 4 ## `not_too_late()`, `can_run()`
        assert job.not_too_late(curr_time) is True
        assert job.can_run(curr_time,set()) is None     # Can't run: Next start is in the future

        curr_time = self.set_test_curr_time("12:00")
        assert job.can_run(curr_time, set()) is True

        # Emulate a conflicting job running
        assert job.can_run(curr_time, {"func_2"}) is None   # Can't run: Waiting for conflicting job to finish
        assert job.status == WAITING    # Status has been set to WAITING

        job.status = RUNNING
        assert job.can_run(curr_time, set()) is False   # Can't run: status not in (TRIGGERED, PENDING, WAITING)


        ## 5 ## `run()` - run time before end-time
        job_result = job.run(curr_time)
        assert isinstance(job_result, JobResult)
        assert job_result.count == 11
        assert job.next_start == curr_time + job.periodicity    # next_start should have been updated
        assert job.last_run == curr_time
        assert job.status == PENDING


        ## 6 ## `trigger_it()`
        temp_time = self.calc_today_time("11:30")
        # Setting fun_args means that `func_2_run` will return 0
        time_changed = job.trigger_it(temp_time, func_args=["X", "Y"])
        assert job.status == TRIGGERED
        assert job.next_start == temp_time
        assert time_changed is True


        ## 7 ## `run()` - run time before end-time
        job_result = job.run(curr_time)
        assert isinstance(job_result, JobResult)
        assert job_result.count == 0
        assert job.next_start == curr_time + job.periodicity    # next_start should have been updated
        assert job.last_run == curr_time
        assert job.status == PENDING


        ## 8 ## `run()` - run time close to end-time; func_2_run raises exception (which is trapped)
        temp_time = self.calc_today_time("11:30")
        # Setting fun_args means that `func_2_run` will raise a ValueError exception
        time_changed = job.trigger_it(temp_time, func_args=[None, None])
        assert job.status == TRIGGERED
        assert job.next_start == temp_time
        assert time_changed is True

        # set current-time such that after running, the calculated next run would exceed end time
        curr_time = self.set_test_curr_time("16:50")
        job_result = job.run(curr_time)
        assert job.last_run == curr_time
        assert job_result.count is None
        assert isinstance(job_result.exception, ValueError)
        assert job.next_start is None
        assert job.status == ENDED
        assert job.priority == NEVER


        ## 9 ## `trigger_remote_job()`
        Job.purge_all_jobs()
        Job.trigger_remote_job("T2", "Serv.Prog", "Func_2_trig", func_args=["a", "b"], func_kwargs={"a": 111})
        jobs = Job.pull_all(pull_name="all_sorted_priority")
        assert len(jobs) == 1
        job = jobs[0]
        assert job.label == "T2"
        assert job.server_prog == "Serv.Prog"
        assert job.func_name == "TRIGGER_Func_2_trig"
        assert job.priority == PRIMER
        assert job.status is None
        assert job.next_start is None
        assert job.func_args == ["a", "b"]
        assert job.func_kwargs == {"a": 111}

    @app_decorator
    def test_03_schedule_methods(self):
        """
        Check that various Schedule methods operate as expected:
            * run_next_pending()
            * sort_jobs()
            * trigger_jobs()

		Not tested explicitly:
            * Schedule() - __init__() - tested as part of `test_01_schedule_initialisation_and_purging()` above
			* add_job() - tested as part of `test_01_schedule_initialisation_and_purging()` above.
			* purge_jobs_for_server_prog() - tested as part of `test_01_schedule_initialisation_and_purging()` above.
			* purge_all_jobs() - tested as part of `test_01_schedule_initialisation_and_purging()` above.
            * trigger_job() - tested as part of `trigger_jobs()`
			* run_schedule() - take too long due to sleep - simulated by run_next_pending() test

        """
        # This test schedule is designed for use with an effective Schedule INITIALISATION TIME of 08:00 (set below)
        test_schedule_spec = [
            # ("Label (unique)", "start-time", interval: mins-integer or string like '10s', '20m' or '3h', "end-time", "process-name", priority-int 1 to 4, "trigger" string or list of strings)
            # If there is no interval then assumed to be a one off event

            # LABEL code: ..SxFxz --> Start & Finish day, where S1/F1: start/finish today, S2/F2: start/finish tomorrow, z --> Status indicator
            ("V1", "17:00", None, "18:00", "shutdown", V_HIGH, None),

            ("H1", "09:00", 360, "16:00", "aaa", HIGH, None),
            ("H2", "09:30", 30, "14:00", "bbb", HIGH, None),

            # Medium status, all with Start time, NO End time, Func name "ccc"
            ("M3", "10:00", 60, "14:00", "ccc", MEDIUM, "M4"),
            ("M4", "10:15", None, "14:00", "ddd", MEDIUM, None),
            ("M5", "10:30", None, "14:00", "eee", MEDIUM, "M3-always"),
        ]
        proc_map = {'aaa': self.aaa,
                    'bbb': self.bbb,
                    'ccc': self.ccc,
                    'ddd': self.ddd,
                    'eee': self.eee,
                    'shutdown': self.shutdown
                    }

        ## 1 ## Test run_next_pending()

        def after_run_fn():
            pass

        test_vals = [
            # (Time,  Expected count of active jobs retrieved,  List of func settings,  Expected result)
            # Func setting list: [func-name, count, str_1, flag, after_run_action_fn, exception]
            ("08:00", 6, ["aaa", 9, None, None, None, ValueError], None),
            ("09:00", 6, None, JobResult("aaa", exception=ValueError("aaa"))),
            ("09:30", 6,["bbb", None, None, None, None, ValueError],
             JobResult("bbb", count=None, func_return=(None, None), exception=ValueError("Raised by bbb..."))),
            ("10:00", 6,["bbb", 4, "B", JobResult.END_JOB, None, None],
             JobResult("bbb", count=4, func_return=(4, "B"), job_flag=JobResult.END_JOB)),
            ("10:05", 5,["ccc", 5, "CC", None, None, None], JobResult("ccc", count=5, func_return=(5, "CC"))),
            ("10:10", 5,[], JobResult("ddd", count=0, func_return=(0, None))),
            ("10:15", 5,[], None),
            ("10:30", 5,[], JobResult("eee", count=0, func_return=(0, None))),
            ("10:31", 5,["ccc", 0, "No trigger", None, None, None],
             JobResult("ccc", count=0, func_return=(0, "No trigger"))),
            ("11:00", 5,["ddd", 44, "D", None, None, None], None),
            ("11:30", 5,["ccc", 8, "Trigger M4", None, after_run_fn, None], None),
            ("11:31", 5,[], JobResult("ccc", count=8, func_return=(8, "Trigger M4"), after_run_action_fn=after_run_fn)),
            ("11:32", 5,[], JobResult("ddd", count=44, func_return=(44, "D"))),
            ("14:05", 2,["aaa", 99, None, None, None, None], None),
            ("15:00", 2,[], JobResult("aaa", count=99)),
            ("17:00", 1,[], JobResult("shutdown", job_flag=JobResult.PURGE_SCHEDULE)),
            ("18:05", 0,[], None),  # 1 Record retrieved from database, but found that ended-date has been reached
            ("18:06", -1,[], None), # No active records retrieved from database
        ]


        self.set_test_curr_time("08:00")
        scheduler = Schedule("App1", "Prog1", test_schedule_spec, self.scheduler_conflicts, proc_map)
        # Replicate run_schedule process - note that function self.aaa only returns `count` or raises exception
        for spoof_time, expected_job_count, run_func_settings, expected_result in test_vals:
            self.set_test_curr_time(spoof_time)
            if run_func_settings:
                self.set_func_return_values(*run_func_settings)
            job_count = scheduler._init_job_structs_from_database()
            assert job_count == expected_job_count
            job_result = scheduler.run_next_pending()
            # print(spoof_time, job_result, expected_result)
            assert str(job_result) == str(expected_result)


        ## 2 ## Test sort_jobs()
        # Spoof current time to be 08:00
        self.set_test_curr_time("08:00")
        scheduler.purge_all_jobs()
        scheduler = Schedule("App1", "Prog1", test_schedule_spec, self.scheduler_conflicts, proc_map)

        sched_med = scheduler.sorted_jobs[MEDIUM]

        expected_med_order = [
            ("M3", self.calc_today_time("10:00")),
            ("M4", self.calc_today_time("10:15")),
            ("M5", self.calc_today_time("10:30"))
        ]
        for ix, job in enumerate(sched_med):
            expected_label, next_time = expected_med_order[ix]
            assert expected_label == job.label
            assert next_time == job.next_start

            # Change next_start times so that scheduler.sorted_jobs[MEDIUM] are no longer in ascending next_start order
            if expected_label == "M4":
                job.next_start = self.calc_today_time("09:30")
            elif expected_label == "M5":
                job.next_start = self.calc_today_time("09:00")

        # Sort the medium priority jobs
        scheduler.sort_jobs([MEDIUM])

        # Confirm jobs now sorted in expected order
        new_med_order = ["M5", "M4", "M3"]
        for ix, job in enumerate(sched_med):
            assert new_med_order[ix] == job.label


        ## 3 ## Test trigger_job()
        # Spoof current time to be 08:30
        self.set_test_curr_time("08:30")
        # Purge & reload schedule
        scheduler.purge_all_jobs()
        scheduler = Schedule("App1", "Prog1", test_schedule_spec, self.scheduler_conflicts, proc_map)

        expected_order = ["H1", "H2", "M3", "M4", "M5", "V1"]
        all_jobs = Job.pull_all(pull_name="all_sorted_nextstart")
        for ix, job in enumerate(all_jobs):
            assert expected_order[ix] == job.label

        # When jobs are triggered their next_start times are set to (spoofed) current-time
        scheduler.trigger_jobs(["H2", "M4"], 1)
        all_jobs = Job.pull_all(pull_name="all_sorted_nextstart")
        expected_order = ["H2", "M4", "H1", "M3", "M5", "V1"]
        for ix, job in enumerate(all_jobs):
            assert expected_order[ix] == job.label

    @app_decorator
    def test_04_schedule_failure_scenarios(self):
        """
        Test problem scenarios.
            * While running schedule, get to point where there are no active jobs (all have ENDED)
            * Exception raised when schedule loaded because no jobs for current server-program
            * Exception raised when schedule loaded because no schedule config is empty
        :return:
        """
        # This test schedule is designed for use with an effective Schedule INITIALISATION TIME of 08:00 (set below)
        test_schedule_spec = [
            # ("Label (unique)", "start-time", interval: mins-integer or string like '10s', '20m' or '3h', "end-time", "process-name", priority-int 1 to 4, "trigger" string or list of strings)
            # If there is no interval then assumed to be a one off event

            # LABEL code: ..SxFxz --> Start & Finish day, where S1/F1: start/finish today, S2/F2: start/finish tomorrow, z --> Status indicator
            ("H1", "09:00", 60, "09:30", "aaa", HIGH, None),    # Expect this should run just once
            ("M1", "09:00", 20, "09:10", "bbb", MEDIUM, None),    # Expect this should run just once
        ]

        log_context = LoggingBufferContext(min_level=INFO, logger_=current_app.logger)
        ## 1 ## Jobs are progressively ENDED after running (because their end-time is reached)
        proc_map = {'aaa': self.aaa, "bbb": self.bbb}
        self.set_func_return_values("aaa", 33, None, None, None, None)
        self.set_test_curr_time("08:00")
        scheduler = Schedule("App1", "Prog1", test_schedule_spec, self.scheduler_conflicts, proc_map, logger=current_app.logger, end_if_no_jobs=True)
        scheduler.sleep_secs = 0    # For test purposes we don't want to sleep during run_schedule()
        with log_context:
            self.set_test_curr_time("09:05")
            run_result = scheduler.run_schedule()
            assert run_result == JobResult.END_SCHEDULE
            assert len(log_context.log_buffer) == 1
            assert log_context.msg_in_buffer(
                "WARNING: [Schedule App1.Prog1] UNEXPECTEDLY ENDING SCHEDULE - No active jobs in the database.")


        ## 2 ## Jobs are progressively ENDED after running (because their end-time is reached) - attempt reload
        proc_map = {'aaa': self.aaa, "bbb": self.bbb}
        self.set_func_return_values("aaa", 33, None, None, None, None)
        self.set_test_curr_time("08:00")
        scheduler = Schedule("App1", "Prog1", test_schedule_spec, self.scheduler_conflicts, proc_map, logger=current_app.logger, end_if_no_jobs=False)
        scheduler.sleep_secs = 0    # For test purposes we don't want to sleep during run_schedule()
        with log_context:
            self.set_test_curr_time("09:05")
            run_result = scheduler.run_schedule()
            assert run_result == JobResult.END_SCHEDULE
            assert len(log_context.log_buffer) == 2
            assert log_context.msg_in_buffer(
                "INFO: [Schedule App1.Prog1] No active jobs in the database. Schedule RELOADED UNEXPECTEDLY (0 jobs active).")
            assert log_context.msg_in_buffer(
                "WARNING: [Schedule App1.Prog1] UNEXPECTEDLY ENDING SCHEDULE - No active jobs in the database.")


        ## 3 ## No jobs for specified server program
        proc_map = {}   # No jobs will be associated with this server program
        self.set_test_curr_time("08:00")
        with log_context:
            with self.assertRaises(NoJobsScheduled):
                scheduler = Schedule("App1", "Prog1", test_schedule_spec, self.scheduler_conflicts, proc_map, logger=current_app.logger)
            assert log_context.msg_in_buffer("WARNING: NO active jobs scheduled for this process.")


        ## 4 ## No jobs in schedule (empty config)
        proc_map = {}
        test_schedule_spec = []     # Empty schedule
        self.set_test_curr_time("08:00")
        with log_context:
            with self.assertRaises(NoJobsScheduled):
                scheduler = Schedule("App1", "Prog1", test_schedule_spec, self.scheduler_conflicts, proc_map, logger=current_app.logger)
            assert len(log_context.log_buffer) == 1
            assert log_context.msg_in_buffer("INFO: ==== NO JOBS SCHEDULED ====")

        print(f"~~~~end~~~~~ INFO {INFO}: ", log_context.level)
        log_context.close()


    @app_decorator
    def test_05_schedule_reload(self):
        """
        Test that schedule reloads at midnight.
            *
        :return:
        """
        pass
