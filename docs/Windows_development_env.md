# Windows Development Environment

IMPORTANT: You will need Windows Administrator permissions in order to install various components.

## Recommended Tools
### GIT
* [Git for Windows](https://git-for-windows.github.io/)
* [Tortoise Git](https://tortoisegit.org/download/)

### IDE
[Pycharm IDE](https://www.jetbrains.com/pycharm/): Community Edition [download](https://www.jetbrains.com/pycharm/download/download-thanks.html?platform=windows&code=PCC).


## Installing Development Environment on Windows

This guide assumes that **PyCharm** Software Development Environment tool is being used for development.

### Elasticsearch

Elasticsearch is used by Harvester process as a temporary datastore. It must be installed and running in order for Router tests to execute successfully.

**Version 8.18.x** is required (note Router may not work with later versions).  [Download Elasticsearch v8.18.2](https://artifacts.elastic.co/downloads/elasticsearch/elasticsearch-8.18.2-windows-x86_64.zip).  

Download the **Zip file** and simply unzip it into target directory.

NOTE: Elasticsearch requires Java JVM server in order to run.

#### Elasticsearch desktop icon

For ease of starting Elasticsearch it is helpful to create a desktop shortcut icon.

The easiest way of doing that is to use Windows Explorer to locate file **_elasticsearch-8.18.2\bin\elasticsearch.bat_**, then Right-click on _**elasticsearch.bat**_ and select _Create shortcut_.

### Java JVM

JVM is part of Java JDK, which can be downloaded and then installed from here:  https://www.oracle.com/technetwork/java/javase/downloads/index.html  (look in Java archive for older versions).

Elasticsearch works fine with **Java SE 11.0.3 (LTS)** - it is not known whether it works OK with more recent versions.



### MySQL

The MySQL Version 8 community edition should be installed - see https://dev.mysql.com/doc/refman/8.0/en/mysql-installer.html.  The web installer is recommended.

The following MySQL components should be installed:
* MySQL Server
* MySQL Workbench - essential client for working with MySQL database
* MySQL Shell [OPTIONAL]
* MySQL Connector/ODBC
* MySQL Connector/Python.

Note that MySQL Server is run as a Windows Service.  It is suggested that you configure it to start automatically when Windows is started.

### Python
Install **Python 3** (you should check which version is currently installed in the PubRouter UAT environment and use that) https://www.python.org/downloads/ - select Windows 64 bit installer.

**NOTE**: Select Custom Installation and tick the box for updating PATH environment variable.

To test Python installation: open a new windows Command window and type: `python -V`.

### Pip installation

Pip (Python package manager) is required: [pip installation](https://pip.pypa.io/en/stable/installation/).

Once the script completes, you can test by typing: `pip -V`.

### Windows Configuration

#### Environment variables

To set an environment, type "_edit environment variables_" in Windows search bar & open panel.

You must set environment variables in order for Router to run successfully on your laptop: 
* `PYTHONPATH=C:\Python\Python38` _adjusted to installed version of python_ (if NOT set by Python installation)
* `PATH=C:\Python\Python38;C:\Python\Python38\Scripts;` _ditto_
* `OPERATING_ENV=development` 
* `JAVA_HOME=C:\Program Files\Java\jdk-11.0.3` (assuming Java version 11.0.3 is installed) if not already set by Java installation process.

#### Hosts file
PubRouter uses a default endpoint for Elasticsearch of `"http://gateway:9200"` (set as Python config variable `ELASTIC_SEARCH_HOST`). For this to work you must add an entry for '''gateway''' to the Windows hosts file.

Open file: `C:\Windows\System32\drivers\etc\hosts` in an editor with Administrator privileges. Add the following entry to it and save.

```
# PubRouter local elasticsearch config
127.0.0.1	gateway
```

### Virtual Environment Installation

####  VirtualEnv tool installation
Open Windows Command panel with Admin privileges: 

* Type *'command'* in Windows search bar
* Click on: _Run as administrator_
   
Install VirtualEnv using pip install:
```buildoutcfg
pip install virtualenv
```

#### Directory for virtual environments
Create a container directory for the virtual environments e.g: `C:\VirtEnv`, within this create a sub directory for Router App:
* `C:\VirtEnv\App`

### Create Router App virtual environment

#### Clone Router repository
Clone Git repo to a directory of your choosing (_PATH-TO-YOUR-GIT-REPO_):
```buildoutcfg
git clone https://github.com/jisc-services/oa-PubRouter-App.git C:\PATH-TO-YOUR-GIT-REPO`

# Update all sub-modules.
git submodule update 
```
   
#### Create Router virtual environment 

Within `C:\VirtEnv` create a sub-directory for Router App:
* `C:\VirtEnv\App`
   
Build the virtual environment:
```buildoutcfg
python -m venv C:\VirtEnv\App
```
   
Activate the environment: 
```buildoutcfg
cd C:\VirtEnv\App

Scripts\activate
```

#### Install application

The Python application is created & installed using PIP.  The Prerequisite components are built first.


```buildoutcfg

# Install Octopus
cd C:\PATH-TO-YOUR-GIT-REPO\oa-PubRouter-App\Octopus
pip install .

# Install Sword2
cd C:\PATH-TO-YOUR-GIT-REPO\oa-PubRouter-App\sword2
pip install .

# Install Router
cd C:\PATH-TO-YOUR-GIT-REPO\oa-PubRouter-App\src
# requirements_4_testing.txt includes packages required for running tests
pip install -r requirements_4_testing.txt
```

#### Create Router Database and Admin user account

The Router database, named 'jper' together with a user account 'jper_user' (which is used for all application database access) must be created by executing the following script:

```buildoutcfg
# Execute script to create 'jper' db & 'jper_user'. 
# If db root user password is NOT supplied then default of 'admin' will be used.
python scripts/create_dev_db.py <root-password>
```

### PyCharm Setup
#### Configure PyCharm

Open your project with PyCharm and link to the App virtual environment created above:

```buildoutcfg
# Menu...
File -> Settings -> Project -> Project Interpreter -> [COG wheel (top right)] -> Add local --> Virtualenv Environment --> Existing environment

# Select existing virtual environment
Python 3.x (App)   C:\VirtEnv\App\Sripts\python.exe

# Apply / OK
```

#### Test Pycharm

Make sure following are running:
* Elasticsearch (run by clicking the Desktop Shortcut you should have created during installation)
* MySQL (should have been started when Windows starts, but if not: search for MySQL Service in Windows list of services and start it).

In PyCharm:
* Run _**web_main**_ (src\router\jper\web_main.py)
* Run _**scheduler**_ (src\router\jper\scheduler.py).

From a browser, navigate to:
* **http://localhost:5998/** (you should be presented with Router home page).
