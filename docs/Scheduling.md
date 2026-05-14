# Router Job Scheduling

NOTE: In this description the terms _process_ and _job_ have the same meaning and are used interchangeably.

All _batch_ processes (aka jobs) in Router are run from a common schedule which is defined in router configuration in `src/router/shared/global_config` directory by the SCHEDULER_SPEC list of tuples in the relevant environment file (e.g. _production.py_), and the SCHEDULER_SLEEP value and SCHEDULER_CONFLICTS dict in _base.py_ . 

This approach ensures that the processing activities are executed in a defined sequence (regardless of server) according to the logical "flow" (Step 1 to Step 4):

| Context                       | Step 1 | Step 2                                                                    | Step 3 | Step 4 | 
|-------------------------------|---|---------------------------------------------------------------------------|---|---|
| **Harvesting**                | Harvest (metadata only) - once per day. | Create unrouted notifications.                                            | Route notifications (create Routed; discard Unrouted). | Send to Repository via SWORD. |
| **Publisher FTP deposits**    | FTP: Move files from jail to temp - regularly throughout day. | Process FTP files (Create unrouted notifications & save files in store). | ditto | ditto |
| **Publisher API submissions** | API submission which creates _Unrouted notification_ & saves any file in store. | N/A                                                                       | ditto | ditto |


In addition to these batch steps, the following Router services are used asynchronously throughout the day:

* Web - Serving web pages (e.g. information, account maintenance etc.)
* API - Publisher submissions - which create _Unrouted notifications_
* API - Repository (CRIS) notification retrieval.


## Programs that use Scheduling

These Router programs using scheduling:
* Scheduler - which runs on both App1 & App2 (but different processes are executed on each server - as determined by Jenkins deployment parameters)
* Harvester
* SWORD-out - when running as a separate application (note that the SWORD-out process is typically run by the Scheduler program).


## Schedule Mechanism Overview

Prior to September 2024 a fixed schedule operated, in which jobs ran at preset times throughout the day; however, this had limitations such as: jobs failing to run when a preceding job overran its timeslot, "dead time" when no jobs were running (wasting available computing resource).

In September 2024 a new flexible scheduling mechanism was introduced, which has the following characteristics:
* The basic job schedule is defined in application config
* The scheduling algorithm is driven by jobs records in the database which are created (from config) whenever a batch application starts running, and are updated as job execution proceeds
* The schedule will automatically reload just after midnight each day (default behaviour of the Schedule class) or alternatively must be reloaded at least once every 24 hours by stopping/starting the applications (this has the benefit of minimising the impact of any memory leaks which is why the Router applications have always been restarted daily).

Jobs are defined with particular attributes - **all of them optional**:
* Job label - required in the case of jobs that may be triggered=
* Job priorities - V. High, High, Medium (default), Low - specified by an integer value 1: V.High, 4: Low.
* Defined start and end times
* Periodicity - i.e. the number of seconds, minutes or hours after which a job is again queued to execute
* Other jobs triggered upon completion - either dependent on the preceding job processing something or in all cases (i.e. irrespective of whether the job processed something or not)
* Conflicting processes - which may be defined to avoid parallel execution. 

These characteristics allow jobs to be scheduled to start running at a defined time and, if required, to repeat at defined intervals until an end-time is reached; additionally or alternatively jobs can be defined to start only when they are triggered by completion of another job.  The following benefits arise:
* Jobs are not skipped if a preceding job takes longer than expected, instead they wait until the preceding job completes
* Pipeline jobs can be conditionally executed only if the preceding job has processed something (avoiding unnecessary execution)
* Maximum use of computing resources can be leveraged
* Jobs are synchronised (including triggering) across servers.

This functionality is primarily coded in the library file: `src/router/shared/models/schedule.py` which relies on Job database table and associated model.
<br>

#### NOTE that the schedules presented in the following sections were correct in November 2024, but should be regarded as indicative as configuration settings may change to meet operational requirements.

## Schedule Conflict Avoidance 

The table shown here is implemented in config as a Dict to prevent certain processes from running in parallel. The rationale is twofold:
* Certain processes are pipelined - i.e. execution of one logically follows another, so it doesn't make sense to let them run in parallel
* Prevent database intensive processes e.g. Adhoc reports from running in parallel with each other to avoid stressing the database.

| Process            | Conflicting processes                             | Notes                                                                             |
|--------------------|---------------------------------------------------|-----------------------------------------------------------------------------------|
| Route harvested    | Harvesting                                        | Route harvested will wait until Harvesting job has finished                       |
| Process FTP files | Route, Route harvested                            | Process FTP will not run while Route or Route harvested is running               |
| Route              | Process FTP files, Route harvested, Adhoc report | Route will not run while Process FTP, Route harvested or Adhoc report is running |
| SWORD-out          | Route, Route harvested, Adhoc report              | SWORD-out will not run while Route, Route harvested or Adhoc report is running    |
| Adhoc report       | Route, SWORD-out, Route harvested                 | Adhoc report will not run while Route, SWORD-out or Route harvested is running    |


## Production Schedule

The schedule has 3 processing "windows" (or zones):
1. Overnight, from **00:15 to 04:20**, are a mixture of recurring processes (see #3 below) plus, importantly, these daily "one-off" processes:
    * **Harvesting** - Harvester process runs, obtaining notifications from Elsevier, PubMed, EPMC & Crossref via their APIs
    * **Routing harvested notifications** - Harvested unrouted notifications_ that are matched to at least 1 repository are saved as _Routed Notifications_.  All Harvested unrouted notifications are deleted after processing
    * **Deleting old data from d/b** - Records meeting certain criteria are purged from particular database tables
    * **Deleting old files from disk** - Files older than defined numbers of days are deleted
    * **Monthly jobs** - Create reports.
    

2. From **04:30 to 08:00**, no scheduled tasks because during this period the following occur:
   * **Database backup** (this is done by AWS Aurora MySQL at preset time).
   * **Database maintenance** (AWS function)
   * **CRIS vendor "window"** (CRISs typically harvest using Router's API from 06:00 - 08:00).
   

3. From **08:00 to 00:15**, are recurring processes:
   * **Move FTP** - Move FTP submissions from _jail_.  Each publisher has an FTP *chroot* directory known as a  _jail_ where they deposit JATS packages. This process moves packages from _jails_ to single location: `/Incoming/ftptmp`.
   * **Process FTP** - Process FTP submissions. _Unrouted notifications_ are created from JATS packages in `/Incoming/ftptmp`
   * **Routing** - _Unrouted notifications_ (from JATS packages or submitted via Router API) that are matched (using Matching config) to at least 1 repository are converted to _Routed Notifications_.  Those that aren't matched are deleted (ditto any related JATS packages)
   * **SWORD Out** - Any newly routed notifications are sent to those matched repositories that are configured to receive them via SWORD2 protocol.

### Production Configuration
NOTE on columns:
* Label - Labels are required for triggering, so the presence of a label generally indicates that the job may be triggered by another
* Start - Indicates the default earliest start time for a job, but a job can be started before this if triggered
* Period - A number in this column indicates a repeating job and specifies the repeat frequency in seconds/minutes/hours.  The next run time is set by (successively) adding the period to the job's last start time until a future start time is achieved; so, say a job has a period of 20 mins, and starts at 09:00 but actually takes 25 mins to run, then the next start time will be set to 09:40 (i.e. the earliest 20 minute interval after job ends) 
* End - A number in this column specifies the latest time that a job may start (note that an already started job may finish running after the _End_ time, but it would not then be able to run again).  Absence of a value generally indicates a one-off job. 
* Process - This is the name of the job
* Priority - Indicates the relative job priority
* Triggers - Value(s) in this column specify the labels of other job(s) that will be triggered when the current job finishes. By default another job will be triggered only if the triggering job has actually produced some output (e.g. moved some files or generated routed notifications) that the downstream (triggered) job is required to process; however, appending "-always" to the job _Label_ causes the downstream job to always be triggered irrespective of the results of the triggering job.

| Label | Start  | Period | End   | Process                                 | Priority | Triggers        | Notes                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
|-------|--------|--------|-------|-----------------------------------------|----------|-----------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
|       | 00:15  |        |       | **harvest**                             | High     | RH1             | **Harvester** process starts at 00:15, obtaining notifications from Elsevier, PubMed, EPMC & Crossref via their APIs. Upon completion it triggers _Route harvested_ (RH1) if some records were harvested. It runs only once.                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| RH1   | 01:00  |        |       | **route_harv** notifications       | High     | SO1, MF1-always | **Route harvested** is triggered by successful completion of _Harvesting_; however there is a possibility that _Harvesting_ might fail part way through (but still produce records to route) which is why _Route harvested_ will run at 01:00 (if it has not already run by being triggered).  Upon completion it triggers both _SWORD-out_ (SO1) if some notifications were routed, and _Move SFTP_ (MF1-always) in all circumstances. It runs only once.<br><br>This process tries to match Harvested unrouted notifications to repositories, thereby creating Routed notifications..<br><br>All Harvested unrouted notifications are deleted after processing. |
| SO1   |        |        | 03:03 | **sword_out** - Send to repository      | Medium   |                 | **SWORD-out** only runs when triggered by _Route harvested_ or _Route_. The latest it can run is 03:03. <br><br>Any newly routed notifications are sent to those matched repositories that are configured to receive them via SWORD2 protocol.                                                                                                                                                                                                                                                                                                                                                                                                                    |
| MF1   | 01:30  | 20 min | 03:03 | **move_ftp** submissions from _jail_    | Medium   | PF1             | **Move FTP** will start at 01:30 unless it has been triggered earlier, and thereafter runs at least every 20 minutes from the time of last execution (if triggered it may run more frequently).  Upon job completion, if any files were moved, it triggers _Process SFTP_. The latest it can run is 03:03. <br><br> Each publisher has an FTP *chroot* directory known as a  _jail_ where they deposit JATS packages. This process moves packages from _jails_ to single location: `/Incoming/ftptmp`.                                                                                                                                                            |
| PF1   |        |        | 03:03 | **process_ftp** submissions             | Medium   | RO1             | **Process FTP** only runs when it is triggered (by _Move SFTP_). Upon completion, if any unrouted notifications were created, it triggers _Routing_. The latest it can run is 03:03. <br><br>This process creates _Unrouted notifications_ from JATS packages in `/Incoming/ftptmp`.                                                                                                                                                                                                                                                                                                                                                                              |
| RO1   | 01:40  | 20 min | 03:03 | **route**                               | Medium   | SO1             | **Routing** will start at 01:40 (unless it has been triggered earlier) and runs at least every 20 minutes from the time of last execution (if triggered it may run more frequently). Upon job completion, if notifications have been routed, it triggers SWORD-out. The latest it can run is 03:03. <br><br>This process tries to match _Unrouted notifications_ (from JATS packages or submitted via Router API) using Matching config to repositories to create _Routed Notifications_.<br><br>Those that aren't matched are deleted along with related JATS packages.                                                                                          |
|       | 03:55  |        |       | **delete_files**                        | V. High  |                 | File deletion runs once at 03:55.<br><br>Files on disk meeting certain age limit criteria are deleted.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
|       | 04:04  |        |       | **delete_old** database records                        | V. High  |                 | Record deletion runs once at 04:04.<br><br>Records meeting certain criteria are purged from particular database tables.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
|       | 04:12  |        |       | **monthly_jobs** (reports)              | V. High  |                 | Monthly jobs are checked one at 04:12<br><br>At the start of each month reports are created for the previous month.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
|       | 04:28  |        |       | **shutdown**                            | V. High  |                 | Application shutdown occurs at 04:28<br><br>All applications running the schedule are exited, whereupon the _supervisorctl_ process restarts them, reloading the schedule afresh.  This is to prevent memory leaks from becoming a serious issue and also refreshes the schedule for the next 24 hours.                                                                                                                                                                                                                                                                                                                                                           |
|       |  |        |       |                                         |          |                 | No batch processes run from 04:30 until 08:00 to allow for database backup, CRIS activity etc.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
|    | 08:00  | 20 min | 23:59 | **move_ftp** submissions from _jail_   | Medium   | PF2             | **Move FTP** will start at 08:00 and repeat every 20 minutes thereafter. Upon completion, if files have been moved it triggers _Process SFTP_. The latest it can run is 23:59.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| PF2   |        |        | 23:59 | **process_ftp** submissions            | Medium   | RO2             | **Process FTP** only runs when triggered by _Move SFTP_. Upon completion, if unrouted notifications have been created it triggers _Routing_. The latest it can run is 23:59.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| RO2   | 08:10  | 20 min | 23:59 | **route**                             | Medium   | SO2             | **Routing** starts at 08:10 (unless triggered earlier) and repeats every 20 minutes. Upon completion, if notifications have been routed it triggers _SWORD-out_. The latest it can run is 23:59.                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| SO2   | 08:15  | 20 min | 23:59 | **sword_out** -Send to repository       | Medium   |                 | **SWORD out** starts at 08:15 and repeats every 20 minutes (unless triggered earlier). The latest it can run is 23:59.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| REP   |        |        | 23:59 | **adhoc_report** - Run any adhoc report | High     |                 | **Adhoc report** only runs when triggered (from the adhoc reporting GUI interface).  The latest it can run is 23:59.<br><br>The purpose of the _Adhoc report_ process is to produce long-running reports that typically take many seconds or minutes to execute (which result in timeout problems if run directly by the GUI web server).                                                                                                                                                                                                                                                                                                                         |
|       |        |        |       |                                         |          |                 |                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |

<br>

## Other environment schedules

Development, Test & Staging/UAT/Pre-production environment have similar schedules configured in their config files, which are tailored to the needs of the particular environment:

* Staging (aka UAT or Pre-production) has an identical schedule to Production
* Test has a restricted schedule to allow for fact that the test servers do NOT run 24x7, but only Monday - Friday, 07:00 to 19:00
* Development is set to run processes more frequently, though in practice batch processes are rarely run in the development environment.
