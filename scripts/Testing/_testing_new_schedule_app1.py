from random import randint
from octopus.core import initialise
from octopus.lib.dates import now_str
from router.shared.models.schedule import Schedule, JobResult, sleep
from router.jper.app import app     # need to import app_decorator as other modules import it from here.


# Dict that PREVENTS key processes from running in parallel (simultaneously)
SCHEDULER_CONFLICTS = {
    # 'key-function-name': ['list-of-functions-that-CANNOT-run-at-the-same-time-as-key-function', ...]
    "route_harv": ["harvest"],
    # E.g. sword-out cannot run in parallel with any of "process_ftp", "route", "route_harv"
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

    # (None, "10:00", 1, "23:59", "shutdown", 1, None),

    # Start > End
    # ("aS1F2a", "11:00", 60, "10:00", "harvest", 2, None),
    # ("aS1F2a", "14:00", 60, "10:00", "harvest", 2, None),
    # ("aS0F2a", "11:00", None, "10:00", "harvest", 2, None),
    # ("aS1F2c", "14:00", None, "10:00", "harvest", 2, None),
    #
    # ("bS2F2a", "08:00", 60, "11:00", "harvest", 2, None),
    # ("bS1F1", "08:00", 60, "14:00", "harvest", 2, None),
    # ("bSxF1", "08:00", 600, "14:00", "harvest", 2, None),
    # ("bS2F2b", "08:00", None, "11:00", "harvest", 2, None),
    # ("bS0F1", "08:00", None, "14:00", "harvest", 2, None),
    #
    # ("cS1a", "11:00", 60, None, "harvest", 2, None),
    # ("cS2", "11:00", None, None, "harvest", 2, None),
    # ("cS1b", "14:00", 60, None, "harvest", 2, None),
    # ("cS1c", "14:00", None, None, "harvest", 2, None),
    #
    # ("dS-F2a", None, 60, "11:00", "harvest", 2, None),
    # ("dS-F2b", None, None, "11:00", "harvest", 2, None),
    # ("dS-F1a", None, 60, "15:00", "harvest", 2, None),
    # ("dS-F1b", None, None, "15:00", "harvest", 2, None),

]
def fn(s, r=None, f=None, e=None):
    num = randint(0, 11)
    start = now_str('%H:%M:%S')
    sleep(num)
    print(f"\n*** Start: {start} {s} ({num})  End: {now_str('%H:%M:%S')} ***\n")
    ret = (num, r) if r else None
    return JobResult(count=num, func_return=ret, job_flag=f, exception=e)

def move_ftp():
    return fn("MOVE FTP")

def proc_ftp():
    return fn("PROCESS FTP")

def other():
    return fn("OTHER")

def _shutdown():
    """
    Terminate the application - causing all scheduler jobs to be PURGED & all database connections be closed.
    """
    return fn("SHUTDOWN", None, JobResult.PURGE_SCHEDULE)



proc_map = {'harvest': other,
            'move_ftp': move_ftp,
            'process_ftp': proc_ftp,
            'delete_files': other,
            'delete_old': other,
            'shutdown': _shutdown}

with app.app_context():
    initialise()
    schedule = Schedule("App1", "testing", SCHEDULER_SPEC, SCHEDULER_CONFLICTS, proc_map, sleep_secs=10)

    end_flag = schedule.run_schedule()
    if end_flag == JobResult.PURGE_SCHEDULE:
        schedule.purge_all_jobs()
    else:
        schedule.purge_jobs_for_server_prog()

