# Router Configuration

Note section below [Config affecting Router operation](#config-affecting-router-operation) that highlights some key config values that affect operation of Router.

## General configuration

### Octopus configuration

Octopus configuration files are located in: `octopus/config` directory.

The configuration that is actually loaded when applications are run is determined, by default, by contents of file: _rootcfg.py_  (`octopus/config/rootcfg.py`), though this can be overridden by contents of Linux Environment variable `APP_CONFIG`.

If `APP_CONFIG` is used, it should contain a dot-path specification to an alternative file, e.g. `"some.other.init_config"` which would cause the configuration loader to use content of `some/other/init_config.py` file, in places of the default _rootcfg.py_.

See `octopus\core.py` function: `load_initial_config()` to understand the process.

### Router configuration files

Router has a *global* set of configuration files plus separate sets for each of the following Router *components*:
* jper
* harvester
* sword-out
* store.

#### Environment sensitive configuration
Each set of configuration files enables support of different deployment environments (development, test, UAT/staging & production) and lives in a _config_.  

Each set comprises:

| Config filename | Content |
|---|---|
| **base.py** | Base configuration, values common across all environments (though values may be overridden by one of the following environment specific files).<br><br>This is always loaded before one of the environment specific files. |
| **development.py** | _Development_ environment configuration. Values may override those in _base.py_.  File can be empty.. |
| **test.py** | _Test_ environment configuration. Values may override those in _base.py_.  File can be empty.. |
| **staging.py** | _UAT/Staging_ environment configuration. Values may override those in _base.py_.  File can be empty.. |
| **production.py** | _Production_ environment configuration. Values may override those in _base.py_.  File can be empty.. |

The *base.py* file is always loaded first, followed by the environment specific file determined by the value of environment variable OPERATING_ENV (which is set by the Jenkins deployment process). For example, `OPERATING_ENV=production` will cause the _production.py_ file to be loaded.

#### Local override (*.cfg) files

In addition to the above "fixed" configuration, it is possible to specify a file which may be loaded from the Jenkins user `/home/jenkins/.pubrouter` directory (or some other location).  This is done by including a `LOCAL_CONFIG` configuration file path in the _base.py_ file.  For example the _base.py_ file in SWORD-out config directory could contain: 
```buildoutcfg
LOCAL_CONFIG = os.path.expanduser("~/.pubrouter/sword-out.cfg")
```
All such *.cfg configuration files are loaded last (after all other configuration.)

#### Component configuration

The sets of configuration files are found in the locations described here.

| Component| Directory | Content |
|---|---|---|
| Global config | `/src/router/shared/global_config` | Global configuration (applicable to all components).  This configuration is loaded before any other. |
| Jper config | `/src/router/jper/config` | Configuration used by Web/API and Scheduler applications. This configuration is loaded after Global config. |
| Harvester config | `/src/router/harvester/config` | Configuration used for Harvester. This configuration is loaded after Global config. |
| SWORD-Out config | `/src/router/jper_sword_out/config` | Configuration for SWORD-Out service. This configuration is loaded after Global config. |
| Store config | `/src/router/store/config` | Configuration for Store service. This configuration is loaded after Global config. |

### Config affecting Router operation

The configuration values listed in this section are IMPORTANT because they modify aspects of Router's operation. There are 2 sets:

1. Configuration in the first table below is set by the Jenkins deployment process & SHOULD NOT be changed manually (unless you are certain you understand the implications).  

2. Configuration in the second table below can be modified to alter aspects of Router's operation.

Note that _Override files_ are located in the `/home/jenkins/.pubrouter` directory.

#### Deployment configuration that should NOT BE MODIFIED manually
Note that in this table, the phrase _current server_ means the server where the configuration file is located.

| Config variable | Location of variable | Purpose & options | Override file |
|---|---|---|---|
| STORE_TYPE | `src/router/shared/global_config/base.py` | Indicates whether the permanent file-store (used for storing article zip packages) is located on the _local_ or the _remote_ App server; this in turn determines whether package (zip) files are accessed directly via OS file functions or indirectly via the Router Store API.<br><br>Values will be either _"local"_ or _"remote"_.<br><br>Set by the Jenkins deployment script (_jenkins_deployment.sh_) depending on parameters passed to Jenkins build job. | `global.cfg` |
| WEB_API_TYPE | `src/router/jper/config/base.py` | Indicates how the Router Web GUI & Router API services are delivered.<br><br>Values will be one of:<br> * _"jper"_ - the Web & API services are being provided on the current server by _jper_ application<br> * _"xapi"_ - the API service is provided by the _xapi_ appication on the current server<br> * _"xweb"_ - the Web service is provided by _xweb_ application on the current server<br> * _"none"_ - no Web/API application is running on the current server.<br><br>Set by the Jenkins deployment script (_jenkins_deployment.sh_) depending on parameters passed to Jenkins build job. | `jper.cfg` |
| SCHEDULER_JOBS | `src/router/jper/config/base.py` | Determines which batch jobs (functions) are run by Scheduler on the current server.<br><br>Will be a list of strings from among this set ("move_ftp", "process_ftp", "route", "route_harv", "sword_out", "monthly_jobs", "adhoc_report", "delete_old", "delete_files", "database_reset", "shutdown").<br><br>Set by the Jenkins deployment script (_jenkins_deployment.sh_) depending on parameters passed to Jenkins build job. | `jper.cfg` |
<br>

#### Operational configuration
These values can be set/adjusted (typically in the indicated local `*.cfg` files or, more permanently, in relevant `.../config/*.py` files) to modify the operational behaviour of Router.

| Config variable | Location of variable | Purpose & options | Override file |
|---|---|---|---|
| ROUTE_ACTION_AFTER_RUN<sup>1</sup> | `src/router/jper/config/base.py` | Determines what happens after the **_route_** or **_route_harvested_** batch job (functions `check_unrouted()` and `check_harvested_unrouted()`) is run by Scheduler.<br><br>See the section [below](#options-for-ACTION_AFTER_RUN-variables) for possible values. | `jper.cfg` |
| SWORD_ACTION_AFTER_RUN<sup>1</sup> | `src/router/jper_sword_out/config/base.py` | Determines what happens after the **_sword_out_** batch job (run by Scheduler) or **_sword-out_** application service finishes a run.<br><br>See the section [below](#options-for-ACTION_AFTER_RUN-variables) for possible values. | `sword-out.cfg` |
| SCHEDULER_SPEC | `src/router/shared/global_config/base.py`<br>`src/router/shared/global_config/production.py`<br>`src/router/shared/global_config/staging.py`<br>`src/router/shared/global_config/test.py` | Determines the batch job (function) timing schedule that is used by the following Router service applications:<br> * Scheduler<br> * SWORD-Out<br> * Harvester. | `global.cfg` |
| MEM_TRACE<sup>1</sup> | n/a | Determines whether Memory Tracing code (used to explore memory leaks) is run or not.  If used, it prints diagnostic information to `supervisor-*-access.log` file(s).<br><br>Allowed values: `True` or `False`.<br><br>NOT recommended for Production environment as memory tracing imposes high operational overhead. If used, should only be set for period of time that memory tracing is required (i.e. don't leave the configuration value set for long periods).  | `global.cfg` |

Notes:
1. Config value was introduced to tackle memory leak issues. 

#### Options for ACTION_AFTER_RUN variables

| Option value | Description | Notes |
|---|---|---|
| None | Do nothing. | Default setting |
| "exit" | Exit process | Causes termination of process (after closing all database connections), which will then be automatically restarted (immediately) by the _**Supervisorctl**_ monitor process (under Linux). |
| "close_conn" | Close ALL database connections. | Should recover memory used by MySQL connector, though in testing difficult to determine if this actually happened. |
| "close_curs" | Close ALL cursors. | Should recover memory used by MySQL connector library, though in testing difficult to determine if this actually happened. |
| "close_class_curs" | Close cursors for a predetermined list of Classes. | Should recover memory used by MySQL connector library, though in testing difficult to determine if this actually happened. |

## MySQL Configuration

For AWS Aurora MySQL  parameter settings - see section *Specific database parameter settings* on [database](./Database.md) page.

### MySQL database and user accounts

NB. On _MySQL Workbench_ application is a useful Windows tool for creating users and reviewing the database table contents etc.  

#### Database & user for normal operation
PubRouter uses a MySQL database (schema) named `jper` which is accessed by User: `jper_user` (which must have access to *jper* database).

The `jper_user` must have the following privileges:
* SELECT
* INSERT
* UPDATE
* DELETE
* EXECUTE
* DROP.

This user MUST be created before running Publications Router.

Execute SQL:

`CREATE USER 'jper_user'@'%' IDENTIFIED BY '...Password...';`

`GRANT DELETE, DROP, EXECUTE, INSERT, SELECT, UPDATE ON jper TO 'jper_user'@'%';`

NB. For development environment there is a script `create_dev_db.py` which automatically creates the database and this user - see here: [Windows development environment](./Windows_development_env.md#create-router-database-and-admin-user-account).

#### Database & superuser for test purposes

For Router's automated testing, it is necessary to have a MySQL superuser account created (in advance):

* Username: `test_admin`
* Required Privileges: `CREATE, CREATE USER, DELETE, DROP, EXECUTE, GRANT OPTION, INDEX, INSERT, SELECT, UPDATE` 
* Match hosts: `%` (all hosts)
* Authentication type: Standard (i.e. username/password)

Execute SQL:

`CREATE USER 'test_admin'@'%' IDENTIFIED BY '...Password...';`

`GRANT CREATE, CREATE USER, DELETE, DROP, EXECUTE, GRANT OPTION, INDEX, INSERT, SELECT, UPDATE ON *.* TO 'test_admin'@'%';`


(This superuser account is used by the test suite to create & destroy test database instances and test users.)

NB. By default it is assumed that MySQL is available at **'localhost'** BUT if this is not the case, for example if it is provided in the cloud (e.g. using AWS Aurora MySQL), then the appropriate connection hoststring must be set in an Environment Variable named: **MYSQL_HOST**.<br>UNIX Example for an RDS instance: `export MYSQL_HOST='dr-oa-test-pubrouter.abcde1234fgh.eu-west-1.rds.amazonaws.com'`

