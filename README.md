# PubRouter-App

## Public release
[Jisc](https://jisc.ac.uk/) released this repository into the public domain under the [GNU General Public License](https://www.gnu.org/licenses/gpl-3.0.en.html) in April 2026 following the decision to retire the Publications Router service on 1 July 2026.

It is one of [three Jisc git repositories](./docs/Git_repos.md) that together store the complete application source code of the final operational version of Publications Router. 

This repository contains the application specific source code, with specific redactions of sensitive configuration data such as email addresses, passwords, IP addresses and database connections.  

## Archived & no longer supported

The repository is archived.
The source code is not supported or maintained by Jisc.  Issues and Pull Requests will not be monitored or responded to.

## Overview

This repository stores the application specific source code (mainly **Python**, with some **JavaScript** and a little **bash shellscript**) of the Jisc Publications Router application (also known as PubRouter or Router), which [Jisc](https://jisc.ac.uk/) developed and operated for 10 years from 2016 to 2026. There are [two other repositories](./docs/Git_repos.md) containing general library code that is used by Publications Router.  

The public website at https://pubrouter.jisc.ac.uk (until July 2026) or via "Way Back Machine" at https://web.archive.org/web/20260220181159/https://pubrouter.jisc.ac.uk/, provides useful overview, including some schematics.

## Documentation Contents

The bulk of the application documentation is in the [./docs](./docs) folder:

* [Other Git repositories used by PubRouter](./docs/Git_repos.md)
* [PubRouter architecture](./docs/Architecture.md)
* [AWS infrastructure](./docs/AWS_infrastructure.md)
* [Database](./docs/Database.md)
* [Configuration](./docs/Configuration.md)
* [Build & Deployment](./docs/Build_Deployment.md)
* [Batch job scheduling](./docs/Scheduling.md)
* [Server administration](./docs/Server_admin.md)
* [Development guidelines](./docs/Development_guidelines.md)
* [Windows development environment](./docs/Windows_development_env.md)

Other documentation is located in a [public Git repository](https://github.com/jisc-services/Public-Documentation/blob/master/PublicationsRouter/README.md#publications-router).  This provides the following important information:
* Detailed description of PubRouter's API (including a Swagger library)
* Detailed description of PubRouter notification JSON data models
* Notes on PubRouter's use of [JATS](https://jats.nlm.nih.gov/publishing/)
* XML structures used by PubRouter to send articles to Eprints & DSpace repositories via SWORD protocol
* Release history.

## Application framework

The PubRouter application is built using the [Flask](https://flask.palletsprojects.com/) framework.  Though some of the software modules in this repository are general purpose and may run in any context, the majority are dependent on the Flask context.

## Application components

PubRouter contains the following principal service components:
* JPER Web - GUI & API web applications
* Scheduler - batch processes
* JPER Harvester - batch harvesting of notifications
* Store - provides services for storing files (article PDFs, Zip files etc.) on disk
* SWORD Out - used to send notifications to Repositories via SWORD protocol.


## PubRouter directory structure

|Directory name| Contents   |
|---|---|
| deployment | Files, arranged in service (component) sub-directories, that are installed onto target servers by the deployment process.<br><br>There is a [README](./deployment/README.md) that describes its contents in more detail. |
| docs | Documentation, mainly *.md file - see Contents section above.   |
| jenkins | Shell scripts used by the Jenkins deployment jobs.   |
| Octopus | Library (submodule) of functions that are used extensively by PubRouter. See [Octopus git repository](https://github.com/jisc-services/oa-PubRouter-Octopus).   |
| scripts | Various scripts, mainly Python, that are used:<br>* as part of particular release deployments (these are in their own 'release_xx.x' sub-directories)<br>* for performing adhoc administration functions.   |
| src | The principal directory containing PubRouter source code, which is packaged into the PubRouter python package.   |
| sword2 | Library (submodule) that provides SWORD2 client & SWORD2 server functionality.   See [SWORD2 git repository](https://github.com/jisc-services/oa-python-sword2).   |
| tests | Full test suite arranged in sub-directories.   |



