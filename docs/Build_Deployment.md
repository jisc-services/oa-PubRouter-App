# Router Build & Deployment

## Overview

Router is built via Jenkins jobs, which generates Router python libraries stored in our PyPi repository.

Router is deployed into target environments (hosted on AWS - see [AWS infrastructure](./AWS_infrastructure.md)) also via Jenkins jobs:
* Test
* UAT / Staging / Pre-production
* Production.

There is 1 Jenkins instances used for deployment (NB. only accessible over Jisc VPN):
* http://jenkins.XXXX.YYYY.jisc.ac.uk

The Jenkins instance runs on a shared AWS server (see [AWS infrastructure shared servers](./AWS_infrastructure.md#shared-servers-across-environments) and [PubRouter Build Tools](https://github.com/jisc-services/oa-PubRouter-Build-Tools/)).

See [here](./Development_guidelines.md) for information on setting up a development environment.


## Manual configuration

### Initial configuration of sudoers on the server
The file named ***etc_sudoers-d_jenkins*** in directory ***oa-PubRouter-App\deployment*** holds sudoers configuration that must be installed (manually) on both App servers as a file named `/etc/sudoers.d/jenkins` and given '0440' permissions: `sudo chmod 0440  /etc/sudoers.d/jenkins`.  

***NB***. This must be installed on new servers BEFORE running Jenkins deployment jobs for the first time.

## PyPi

Router service relies on the following bespoke python packages stored on the PyPi server.

| Package name | Corresponding GitHub repository  | 
|-----|-----|
| router  | https://github.com/jisc-services/oa-PubRouter-App |
| octopus | https://github.com/jisc-services/oa-PubRouter-Octopus |
| pythons-sword2 | https://github.com/jisc-services/oa-python-sword2 |

These packages are built using Jenkins build jobs and are used by the Jenkins deployment jobs.  The package version number is derived from content of VERSION file at the root of each corresponding Git repository. 

Development (Dev) and Production (Live) versions of packages are segregated in different folders on the PyPi server:
* **/var/local/router_pypi/dev_packages** - packages in this directory will be overwritten each time a (test) version of the application is built. You can view/access via URL: http://dev_pypi.XXXX.YYYY.jisc.ac.uk/ (only over Jisc VPN)
* **/var/local/router_pypi/live_packages** - packages in this directory are created when Live (Prod) packages are built, and cannot normally be overwritten (though there is a parameter on the Jenkins job that enables overwriting).  You can view/access via URL: http://live_pypi.XXXX.YYYY.jisc.ac.uk/ (only over Jisc VPN).

More detail here: [Application deployment architecture](Architecture.md#router-bespoke-python-packages).

## Jenkins

### Jenkins configuration in Gitlab repo

Jenkins configuration is maintained in a git repository stored on Jisc's GitLab server: https://XXXX.YYYY.jisc.ac.uk/open-access/jenkins-config-backup.

Any changes made to Jenkins jobs (via Jenkins GUI) are automatically pushed to the _'latest-config'_ branch in the git repo on a weekly basis via a cron job on the Jenkins server.

### Jenkins jobs

[Jenkins](http://jenkins.XXXX.YYYY.jisc.ac.uk/) is used to build, test, create PyPi packages & deploy Router onto:
* Test environment
* Stage (aka UAT/Pre-production) environment
* Production (Live) environment.


Jobs are grouped under these headings:
* Router TEST - Jobs to build & deploy application into Test environment
* Router STAGE - Jobs to build & deploy application into Stage environment
* Router LIVE - Job to deploy application into Prod environment.


A note on **Job Names**:
* Names beginning with underscore '_' are Jenkins Pipeline jobs
* Names without underscore prefix are conventional Jenkins jobs.



### Test jobs
Each of the "…\_build\_…" Jenkins jobs creates a DEV PyPi package, which is uploaded to the PyPi repository.

| Job name | Description  | Notes    |
|---|----|----|
| _ROUTER_build_DEV-pkg_deploy_TEST  | Build  _Dev_ Router package, add to PyPi repo, deploy onto App1 & App2 Test servers:<br>* Extract and build particular branch of App from github  (default: _development_ branch)<br>* Run tests (if ROUTER_RUN_TESTS is True)<br>* Create DEV Router package in PyPi repository (always overwrites any existing package)<br>* Deploy Router to both App1 & App2 Test servers.<br><br>The job takes the following parameters:<br>* GIT_REF<br>* ROUTER_RUN_TESTS<br>* SERVICES_APP1<br>* SCHEDULER_JOBS_APP1<br>* SERVICES_APP2<br>*  SCHEDULER_JOBS_APP2<br><br>See [Jenkins parameters](#jenkins-parameters) below for details.  | PyPi is updated with new DEV *router* package.    |
| _ROUTER_deploy_DEV-pkg_to_STAGE | Deploy _Dev_ package (specified by GIT_REF) onto App1 & App2 Stage (UAT) servers. <br><br>The job takes the following parameters:<br>* GIT_REF<br>* SERVICES_APP1<br>* SCHEDULER_JOBS_APP1<br>* SERVICES_APP2<br>*  SCHEDULER_JOBS_APP2<br><br>See [Jenkins parameters](#jenkins-parameters) below for details.  | This is useful for preliminary UAT test purposes, without building the "Live" python package. |
| OCTOPUS_build_TEST-pkg | Build a DEV package for Octopus and upload it to PyPi repository.<br><br>By default builds *development* branch & runs tests before building package.  | PyPi is updated with new DEV *octopus* package.   |  |
| SWORD2_build_TEST-pkg | Build a DEV package for Python-Sword2 and upload it to PyPi repository.<br><br>By default builds *development* branch & runs tests before building package.  | PyPi is updated with new DEV *python-sword2* package.    |
| <br>**Subsidiary shared jobs** | <br>**Jobs that are called by the main jobs listed above. Do NOT run job directly.**  |    |
| _x_pipeline_ROUTER | This is a generic job, called by other pipeline jobs: __ROUTER_build_DEV-pkg_deploy_TEST_  and __ROUTER_build_LIVE-pkg_deploy_STAGE_ which, depending on parameter values:<br/>* Extracts and builds a particular branch of the App from github  (default: _development_ branch)<br>* Run tests (if ROUTER_RUN_TESTS is True)<br>* Create DEV or LIVE Router package in PyPi repository (depending on parameter BUILD_LIVE)<br>* Deploy Router  to both App1 & App2 Test or Stage servers (depending on ENVIRONMENT parameter).<br><br>The job takes the following parameters:<br>* ENVIRONMENT<br>* GIT_REF<br>* ROUTER_RUN_TESTS<br>* BUILD_LIVE<br>* OVERWRITE_PKG<br>* SERVICES_APP1<br>* SCHEDULER_JOBS_APP1<br>* SERVICES_APP2<br>*  SCHEDULER_JOBS_APP2<br><br>See [Jenkins parameters](#jenkins-parameters) below for details. | PyPi is updated with new DEV or LIVE *router* package.    |
<br>

### Stage jobs
Each of the "…\_build\_…" Jenkins jobs creates a LIVE PyPi package, which is uploaded to the PyPi repository.

|  Job name  | Description    | Notes    |
|---|----|----|
| _ROUTER_build_LIVE-pkg_deploy_STAGE | Build  _Live_ Router package, add to PyPi repo, deploy onto App1 & App2 Stage (UAT) servers:<br>* Extract and build particular branch of App from github  (default: _development_ branch)<br>* Run tests (if ROUTER_RUN_TESTS is True)<br>* Adds LIVE Router package to PyPi repository if it doesn't yet exist there or if OVERWRITE_PKG is True<br>* Deploy Router to both App1 & App2 Stage (UAT) servers.<br><br>The job takes the following parameters:<br>* GIT_REF<br>* OVERWRITE_PKG<br>* ROUTER_RUN_TESTS<br>* SERVICES_APP1<br>* SCHEDULER_JOBS_APP1<br>* SERVICES_APP2<br>*  SCHEDULER_JOBS_APP2<br><br>See [Jenkins parameters](#jenkins-parameters) below for details. | PyPi is updated with new LIVE *router* package.    |
| _ROUTER_deploy_DEV-pkg_to_STAGE  | *See Job entry in Test jobs table above.*    |    |
| OCTOPUS_build_LIVE-pkg  | Build a _Live_ package for PubRouter-Octopus and upload to PyPi repository (if it doesn't yet exist there or if OVERWRITE_PKG is True).<br><br>Always uses latest release TAG and runs tests before building package.<br><br>The job takes the following parameters:<br>* OVERWRITE_PKG    | PyPi is updated with new LIVE *octopus* package.    |
| SWORD2_build_LIVE-pkg  | Build a _Live_ package for Python-Sword2 and upload it to PyPi repository (if it doesn't yet exist there or if OVERWRITE_PKG is True).<br><br>Always uses latest release TAG and runs tests before building package.<br><br>The job takes the following parameters:<br>* OVERWRITE_PKG    | PyPi is updated with new LIVE *python-sword2* package. |
| <br>**Subsidiary shared jobs**  | <br>**Jobs that are called by the main jobs listed above. Do NOT run job directly.**    |    |
| _x_pipeline_ROUTER  | *See Job entry in Test jobs table above.*    |    |
<br>

### Live jobs

| Job name | Description | Notes    |
|---|---|----|
| _ROUTER_deploy_LIVE | Principal job for deploying Router onto App1 & App2 **production** servers.<br><br>Takes the following parameters:<br>* GIT_REF<br>* SERVICES_APP1<br>* SCHEDULER_JOBS_APP1<br>* SERVICES_APP2<br>*  SCHEDULER_JOBS_APP2<br><br>See [Jenkins parameters](#jenkins-parameters) below for details.| Deploys to App2 first, and App1 second.<br><br>For quickest deployment, the Jenkins live App2 & App1 nodes should be started manually. |
<br>


### Jenkins parameters

| Parameter name | Description|
|---|---|
| GIT_REF | Git release Tag to deploy. |
| ROUTER_RUN_TESTS | Boolean value that determines if tests are to be run. |
| ENVIRONMENT | Environment into which router is to be deployed: 'Test' or 'Stage'. |
| BUILD_LIVE | Boolean value that determines if DEV or LIVE package is to be built. |
| OVERWRITE_PKG | Boolean value that determines if an existing LIVE package can be overwritten (default is FALSE). |
| SERVICES_APP1 | Defines which Router application services will be built/deployed on **App1** - should consist of strings from this set:  _'jper'_ or _'xweb'_, _'harvester'_, _'scheduler-ftp'_, _'scheduler'_, _'sword-out'_, _'store-app'_, _'no-store'_  concatenated with '&#124;' (see [Services keywords](#services-keywords) below).<br><br>For example: _jper&#124;scheduler-ftp&#124;harvester_. |
| SCHEDULER_JOBS_APP1 | If _'scheduler-ftp'_ or _'scheduler'_  is included in the SERVICES_APP1 string, then this parameter defines which Jobs are to be run by the Scheduler on App1.<br>(See [Scheduler job keywords](#scheduler-job-keywords) below).<br><br>For example: _move_ftp&#124;process_ftp&#124;monthly_jobs&#124;adhoc_report&#124;delete_old&#124;delete_files&#124;database_reset&#124;shutdown_.|
| SERVICES_APP2 | Defines which Router application services will be built/deployed on **App2** - should consist of strings from this set:  _'xapi'_, _'harvester'_, _'scheduler'_, _'sword-out'_, _'store-app'_, _'no-store'_  concatenated with '&#124;' (see [Services keywords](#services-keywords) below).<br><br>For example: _sword-out&#124;store-app&#124;scheduler_. |
| SCHEDULER_JOBS_APP2 | If _'scheduler'_ is included in the SERVICES_APP2 string, then this parameter defines which Jobs are to be run by the Scheduler on App2.<br>(See [Scheduler job keywords](#scheduler-job-keywords) below).<br><br>For example: _route&#124;route_harv&#124;delete_files&#124;database_reset&#124;shutdown_.|
<br>

#### Services keywords 
SERVICES_APP1 or SERVICES_APP2 parameters are specified as a concatenated string of values from the following table separated by a '&#124;' character.  For example: '`jper|scheduler-ftp|harvester`'.  This string determines which application services are run on a server as self-contained Python Applications.

| Service keyword | Meaning | Note|
|---|---|---|
| jper<sup>1</sup> | Run the JPER Web + API application (provides Router GUI & Router API). | Run on App1 server. Gateway NGINX must be configured to route Web & API traffic to this server. |
| xweb<sup>1</sup> | Run the JPER Web application (provides Router GUI). | Run on App1 server.  Gateway NGINX must be configured to route Web traffic to App1 server. |
| xapi<sup>1</sup> | Run the JPER API application (provides Router API). | Run on App2 server.  Gateway NGINX must be configured to route API traffic to App2 server. |
| harvester | Run the Harvester application. | Run on just one App server. |
| scheduler-ftp | Run the Scheduler application on the SFTP server (App1). | Must be used if the Scheduler is running on the SFTP server. |
| scheduler | Run the Scheduler application on the Non-SFTP server (App2). | Must be used if the Scheduler application is running on the server which does NOT provide the SFTP service.|
| sword-out | Run the SWORD-Out application. | Run on just one App server.<br><br>An alternative to running SWORD-Out as a self-contained application is to run it as a Scheduler job instead (see _sword_out_ in _Scheduler job keywords_ section below).  |
| store-app | Run the Store API application on the server with long-term file store ('Incoming/store' directory) - currently App2 server. | Mutually exclusive with _'no-store'_. |
| no-store | If used, indicates that Router is being deployed on a SINGLE App server, and so NO Store API application is needed. | Mutually exclusive with _'store-app'_. |

NOTES:
1. Service _jper_ is mutually exclusive with _xweb_ and _xapi_ - it runs a gunicorn webserver (on App1) that provides both GUI & API endpoints.  As an alternative to this, the GUI & API can be split across App1 & App2 servers - with service _xweb_ run on App1 and _xapi_ on App2 (this requires Gateway NGINX to route traffic accordingly).<br><br>(Names can be remembered - _xweb_: "exclusive Web", _xapi_: "exclusive API").  
<br>

#### Scheduler job keywords 
SCHEDULER_JOBS_APP1 or SCHEDULER_JOBS_APP2 parameters are specified as a concatenated string of values from the following table, each separated by a '&#124;' character.  For example: '`move_ftp|process_ftp|monthly_jobs|adhoc_report|delete_old|delete_files|database_reset|shutdown`'.  

This string determines which jobs (functions) are run by the Scheduler application on the particular App server.

Note that the master schedule for all jobs (that run across both App servers) is defined by the SCHEDULER_SPEC  (list of tuples) configuration value that is defined in the `src/router/shared/global_config` directory for the relevant environment.

| Scheduler job keyword | Meaning  | Note|
|---|---|---|
| move_ftp | Run the process that moves JATS packages deposited in a publisher's SFTP directory to the temporary directory: `Incoming/ftptmp`. | Can only be run on the SFTP App server (App1). |
| process_ftp | Run the process that processes JATS packages in the  `Incoming/ftptmp` directory and creates _Unrouted notifications_ (in _notification_ db table) and stores the package in the long-term file store.  | Can only be run on the SFTP App server (App1). |
| route | Run the process that attempts to match _Unrouted notifications_ (in _notification_ db table) to particular *repository* accounts (using Matching parameters) which, if successful, results in a *Routed notification* or if not, results in the _Unrouted notification_ and any associated file package being deleted. | Can run on either App server. May be more efficient to run it on the server with the long term file store (which avoids use of Store API to delete unrouted packages). |
| route_harv | Run the process that attempts to match Harvested _Unrouted notifications_ (in _harvested_unrouted_ db table) to particular *repository* accounts (using Matching parameters) which, if successful, results in a *Routed notification* being created in the _notification_ db table.  | At the end of this process, the _harvested_unrouted_ db table is emptied (usually by truncation, but possibly by deleting processed records if unprocessed records remain - e.g. if added by a concurrent Harvesting job ). |
| sword_out | Run the SWORD-Out process that sends notifications to Repositories. | An alternative to this mechanism is to run SWORD-Out as an independent App service (see _sword-out_ in _Services keywords_ section above). |
| monthly_jobs | Runs the monthly reporting jobs.  | Should be run only on the server where Web application runs (App1) because it writes report files (that are served by Web app) to disk. |
| adhoc_report | Runs the ad hoc reporting job.  | Should be run only on the server where Web application runs (App1) because it writes report files (that are served by Web app) to disk. |
| delete_old | Housekeeping job that deletes old **database** records that meet deletion criteria - retention period and, possibly, status.  | The tables affected, the retention period and the database deletion query names are specified in the SCHEDULED_DELETION_DICT configuration parameter.  (The deletion queries themselves are specified in the `mysql_dao.py` file for each affected database table).<br><br>Should be run on only ONE server (App1 or App2). |
| delete_files | Housekeeping job that deletes old files from file-system.  | Should be run on BOTH application servers (App1 & App2).  Different directories are affected and different criteria (age of files) apply on each server. |
| database_reset | Causes all database connections to be reset. | Provided as a mechanism to clear out unused connections, recover RAM. |
| shutdown | Causes Scheduler process to exit.  Note that it is immediately restarted by the **supervisorctl** (which runs the service under Linux).  | Provided to mitigate server _Out of Memory_ problems which have affected Scheduler (& otherwise remain unresolved). |
<br>


### Jenkins deployment scripts

Deployment (via Jenkins) is managed by 2 bash shell-scripts, which are called with appropriate parameters by the Jenkins jobs noted above:
* [jenkins/jenkins_build.sh](../jenkins/jenkins_build.sh)
* [jenkins/jenkins_deployment.sh](../jenkins/jenkins_deployment.sh)

