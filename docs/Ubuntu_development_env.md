# Ubuntu Development Environment

IMPORTANT: You will need Linux Administrator permissions in order to install various components.

These instructions are based on using **Ubuntu 24.04.4 LTS**.

## Recommended Tools
### GIT
* Standard Git - Install: `sudo apt-get install git`

### IDE - Pycharm
* [Pycharm IDE](https://www.jetbrains.com/pycharm/): Community Edition (this is now combined with professional edition) - Install SNAP version via Ubuntu **App Centre**.


## Installing Development Environment on Ubuntu

This guide assumes that **PyCharm** Software Development Environment tool is being used for development.

### Elasticsearch

Elasticsearch [ES] is used by Harvester process as a temporary datastore. It must be installed and running in order for Router tests to execute successfully.

**Version 8.18.x** is required (note Router may not work with later versions). 

It is recommended that a Docker instance of ES is used in development.  This requires installation of Docker, followed by installation of the ES Docker image.  See general information on [installing Elasticsearch with Docker](https://www.elastic.co/docs/deploy-manage/deploy/self-managed/install-elasticsearch-with-docker).

Follow these steps in the [Development installation quickstart guide](https://www.elastic.co/docs/deploy-manage/deploy/self-managed/local-development-installation-quickstart):
* Install **Docker Desktop** - follow [instructions here](https://docs.docker.com/desktop/setup/install/linux/ubuntu/).  When starting Docker Desktop, select _Personal_ use; you can skip creating an account (i.e. use it anonymously). Update the **Resources** settings to:
  * (optionally) reduce CPU limit (e.g. from 4 to 2)
  * reduce Disk usage (by default it will try to grab the whole disk) - 64GB is ample, you can probably set less
  * (optionally) reduce Memory and Swap limits
  * enable resource saver after 30 seconds
* Install ES image appropriate for laptop hardware (AMD64 is for AMD or Intel chips) [ES 8.18.8-amd64](https://www.docker.elastic.co/r/elasticsearch/elasticsearch:8.18.8-amd64): 
  * In a terminal window: `docker pull docker.elastic.co/elasticsearch/elasticsearch:8.18.8-amd64`
* Run ES:
  * In a terminal window: `docker run --name pubrouter --net elastic -p 9200:9200 -it -m 512MB docker.elastic.co/elasticsearch/elasticsearch:8.18.8-amd64` (the setting `-m 512MB` limits memory usage)
  * If you get ERROR: `"Error": "failed to set up container networking: network elastic not found"`, then do the following:
    * Create network: `docker network create elastic`
    * Start the container: `docker start pubrouter`
* In _Docker Desktop_ you should see the _pubrouter_ container running.


### MySQL

Install the Ubuntu MySQL server - See https://ubuntu.com/server/docs/how-to/databases/install-mysql/

By default when MySQL server is installed, a user named **root** is created, but without a password, for administering the database from SQL command line. 

#### MySQL Workbench

Install **MySQL Workbench Community Edition** - install SNAP version via Ubuntu **App Centre**.

#### Create *root2* user

An application script requires a root user which can be authenticated from python script, so a second user named **root2** must be created (with password *admin*).

```
# Run MySQL command line
sudo mysql -u root

# mysql>  terminal window is displayed

# Copy & run these 4 SQL statements

CREATE USER root2@localhost IDENTIFIED WITH caching_sha2_password BY 'admin';

GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, RELOAD, SHUTDOWN, PROCESS, FILE, REFERENCES, INDEX, ALTER, SHOW DATABASES, SUPER, CREATE TEMPORARY TABLES, LOCK TABLES, EXECUTE, REPLICATION SLAVE, REPLICATION CLIENT, CREATE VIEW, SHOW VIEW, CREATE ROUTINE, ALTER ROUTINE, CREATE USER, EVENT, TRIGGER, CREATE TABLESPACE, CREATE ROLE, DROP ROLE ON *.* TO `root2`@`localhost` WITH GRANT OPTION;

GRANT ALLOW_NONEXISTENT_DEFINER,APPLICATION_PASSWORD_ADMIN,AUDIT_ABORT_EXEMPT,AUDIT_ADMIN,AUTHENTICATION_POLICY_ADMIN,BACKUP_ADMIN,BINLOG_ADMIN,BINLOG_ENCRYPTION_ADMIN,CLONE_ADMIN,CONNECTION_ADMIN,ENCRYPTION_KEY_ADMIN,FIREWALL_EXEMPT,FLUSH_OPTIMIZER_COSTS,FLUSH_PRIVILEGES,FLUSH_STATUS,FLUSH_TABLES,FLUSH_USER_RESOURCES,GROUP_REPLICATION_ADMIN,GROUP_REPLICATION_STREAM,INNODB_REDO_LOG_ARCHIVE,INNODB_REDO_LOG_ENABLE,OPTIMIZE_LOCAL_TABLE,PASSWORDLESS_USER_ADMIN,PERSIST_RO_VARIABLES_ADMIN,REPLICATION_APPLIER,REPLICATION_SLAVE_ADMIN,RESOURCE_GROUP_ADMIN,RESOURCE_GROUP_USER,ROLE_ADMIN,SENSITIVE_VARIABLES_OBSERVER,SERVICE_CONNECTION_ADMIN,SESSION_VARIABLES_ADMIN,SET_ANY_DEFINER,SHOW_ROUTINE,SYSTEM_USER,SYSTEM_VARIABLES_ADMIN,TABLE_ENCRYPTION_ADMIN,TELEMETRY_LOG_ADMIN,TRANSACTION_GTID_TAG,XA_RECOVER_ADMIN ON *.* TO `root2`@`localhost` WITH GRANT OPTION;

GRANT PROXY ON ``@`` TO `root2`@`localhost` WITH GRANT OPTION;

# Quit
quit
```

### Python

Python v3 should already be present on the Ubuntu system.

To test Python installation: open a new windows Command window and type: `python3 -V`.

### Pip installation

Pip (Python package manager) is required.  This should be available once PyCharm is installed and a virtual environment configured (see later).  But if you find it isn't then follow these instructions: [pip installation](https://pip.pypa.io/en/stable/installation/).

### Configuration

#### Flask environment variables

The `.flaskenv` file (which should already be located in the project root directory) can be edited to include environment specific values that are imported into Flask config.

The essential value to include in the development environment is:
* `OPERATING_ENV=development` 

#### Hosts file
PubRouter uses a default endpoint for Elasticsearch of `"http://gateway:9200"` (set as Python config variable `ELASTIC_SEARCH_HOST`). For this to work you must add an entry for '''gateway''' to the _hosts_ file.

In `/etc/hosts` add the following entry:
```
# PubRouter local elasticsearch config
127.0.0.1	gateway
```

### Download Git repository & Create operational virtual environment

**This is most easily accomplished from within Pycharm**, which is what the following steps assume.  (This differs from the documented approach described for [Windows](../Windows_development_env.md)) which creates Virtual environment outside of Pycharm.


1. Run **Pycharm**

From within Pycharm...

2. Download the repository from Github:
    * _File_ > _Project from Version Control..._ 
    * Clone the repository by URL: `https://github.com/jisc-services/oa-PubRouter-App` (this will also clone the Github module dependencies: Octopus and Sword2).  You can keep default Directory.

You should see the *oa-PubRouter-App* project tree, which includes the *Octopus* and *sword2* components that were automatically cloned from GitHub.

You are also likely to see a Warning notice: "No Python interpreter cocnfigured for router"with options to *Create a virtual environment using requirements.txt* or *Custom Environment*.

3. Create interpreter environment:

* Select *Custom Environment* and accept all defaults (*Generate new*, *Virtualenv* etc.)

4. Build the libraries

    * On Pycharm bottom left vertical toolbar, click the ***Terminal*** icon;  alternatively press Alt+F12.  The terminall window should open, with `(.venv) ...` displayed

    * Run the following commands in the terminal window

```buildoutcfg

# Build Octopus library
cd Octopus
pip install .

# Build Sword2 library
cd ../sword2
pip install .

# Build Router library
cd ..
pip install .

# Install additional packages needed for testing
pip install -r requirements_4_testing.txt
```
<br>

#### Create Router Database and Admin user account

The Router database, named 'jper' together with a MySQL user account 'jper_user' (which is used for all application database access) and a Router administrator account must be created by executing the script  **create_database.py** (in scripts directory) from the PyCharm terminal window.

From the Pycharm Terminal window (Alt+F12)...
```
# Change to scripts directory
cd ~/PycharmProjects/oa-PubRouter-App/scripts

# Run the script passing MySQL user name 'root2'
python -m create_database root2

# This may take a little while
```
<br>

#### Add necessary File-system directories

Create the following directory tree structure and make all directories r/w by all:
```
# Required directory structure (/Incoming with sub-direcctories)
/Incoming
      /app_local_store
      /ftperrors
      /ftptmp
      /logs
      /reports
      /store  
      /sftpusers
      /tmparchive
```

```bash
# As root user ....
sudo mkdir /Incoming
sudo chmod -R g+w,o+w /Incoming

sudo cd /Incoming

# Create sub-directories under /Incocming
sudo mkdir app_local_store
sudo mkdir ftperrors
sudo mkdir ftptmp
sudo mkdir logs
sudo mkdir reports
sudo mkdir store  
sudo mkdir sftpusers
sudo mkdir tmparchive

chmod -R g+w,o+w *
```


#### Test Pycharm

Make sure following are running:
* Elasticsearch (check that the `pubrouter` docker container is running - in the Docker Desktop)
* MySQL (from a linux terminal enter: `ps -ef|grep mysql` and look for a line containing: `/usr/sbin/mysqld`)

In PyCharm:
* Run _**web_main**_ (src/router/jper/web_main.py)
* Optionally run _**scheduler**_ (src/router/jper/scheduler.py).

From a browser, navigate to:
* **http://localhost:5998/** (you should be presented with Router home page)
* You should log in as Administrator with username / password:  `admin` / `admin`.
