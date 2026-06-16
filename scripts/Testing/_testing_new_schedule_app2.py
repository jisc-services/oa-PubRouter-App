from random import randint
from octopus.core import initialise
from octopus.lib.dates import now_str
from router.shared.models.schedule import Schedule, JobResult, sleep
from router.jper.app import app     # need to import app_decorator as other modules import it from here.


# Dict that prevents key processes from running in parallel (simultaneously)
SCHEDULER_CONFLICTS = {
    # 'function-name': ['list-of-functions-that-CANNOT-run-at-the-same-time', ...]
    "route_harv": ["harvest"],
    "sword_out": ["process_ftp", "route", "route_harv"],
    "process_ftp": ["route", "sword_out", "route_harv"],
    "route": ["process_ftp", "sword_out", "route_harv"]
}

SCHEDULER_SPEC = [
    # ("Label (unique)", "start-time", interval: mins-integer or string like '10s', '20m' or '3h', "end-time", "process-name", priority-int 1 to 4, "trigger" string or list of strings)
    # If there is no interval then assumed to be a one off event

    ## IOP tend to deposit from midnight. Usually takes 2.5 - 3 hours to complete.

    # IMPORTANT: The ES server used by 'harvest' is STARTED at Midnight and STOPPED at 02:30 a.m. each night.
    (None, "00:15", None, None, "harvest", 2, "RH1"),
    ("XRH1", "01:00", None, None, "route_harv", 2, ["XSO1", "XMF1-always"]),  # Route following harvesting
    ("XSO1", None, None, "03:00", "sword_out", None, None),
    ("XMF1", "01:30", 30, "03:00", "move_ftp", None, "XPF1"),
    ("XPF1", None, None, "03:00", "process_ftp", None, "XRO1"),
    ("XRO1", "02:00", 30, "03:00", "route", None, "XSO1"),  # This may route a lot of IOP stuff
    (None, "03:55", None, None, "delete_files", 1, None),
    (None, "04:04", None, None, "delete_old", 1, None),
    (None, "04:12", None, None, "monthly_jobs", 1, None),  # Reporting
    # "",  ("04:20", None, None, "database_reset"),       # Daily reset (close database connections)
    (None, "04:28", None, None, "shutdown", 1, None),  # Exit the application after closing database connections
    # (supervisord then automatically restarts it) -
    # this to remedy any memory leaks
    # AWS window
    # ("", "04:30", None, None, "db_backup", None, None),       # Done by AWS RDS - allow 30 mins
    # ("", "05:00", None, None, "db_maintenance", None, None),    # Weekly AWS RDS maintenance window - allow 1 hour

    # CRIS vendor window - CRISs tend to harvest from 06:00-08:00

    ("XMF2", "08:00", "20s", "23:59", "move_ftp", None, "XPF2"),
    ("XPF2", None, None, "23:59", "process_ftp", None, "XRO2"),
    ("XRO2", "08:30", "20s", "23:59", "route", None, "XSO2"),
    ("XSO2", "08:35", "20s", "23:59", "sword_out", None, None),
    ("ZZ", None, None, "20:36", "sword_out", None, None),
]


def fn(s, r=None, f=None, e=None):
    num = randint(0, 11)
    start = now_str('%H:%M:%S')
    sleep(num)
    print(f"\n*** Start: {start} {s} ({num})  End: {now_str('%H:%M:%S')} ***\n")
    ret = (num, r) if r else None
    return JobResult(count=num, func_return=ret, job_flag=f, exception=e)

def route():
    return fn("ROUTE", 123)

def route_h():
    return fn("ROUTE HARVESTED", 555)

def sword_out():
    # return fn("SWORD OUT", f=JobResult.END_JOB)
    return fn("SWORD OUT")

def _shutdown():
    return fn("SHUTDOWN", None, JobResult.END_SCHEDULE)

def other():
    return fn("OTHER")


proc_map = {'route': route,
            'route_harv': route_h,
            'sword_out': sword_out,
            'delete_files': other,
            'delete_old': other,
            'shutdown': _shutdown}
with (app.app_context()):
    try:
        initialise()
        schedule = Schedule("App2", "testing", SCHEDULER_SPEC, SCHEDULER_CONFLICTS, proc_map, sleep_secs=10, end_if_no_jobs=False)
        end_flag = schedule.run_schedule()
        if end_flag == JobResult.PURGE_SCHEDULE:
            schedule.purge_all_jobs()
        else:
            schedule.purge_jobs_for_server_prog()
    except Exception as e:
        print("\n**** TERMINATING with exception: ", repr(e))
        raise e
