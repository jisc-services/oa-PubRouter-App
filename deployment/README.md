# Contents of 'deployment' directory

**NOTE: The `jenkins_deployment.sh` script found in the [Jenkins schellscript directory](../jenkins) will correctly install all these configuration files into the appropriate directories on the server, when run under the auspices of Jenkins - see the [Build tools repository](https://github.com/jisc-services/oa-PubRouter-Build-Tools).**

The `deployment` directory holds the following files:
* Deployment configuration files (used by gunicorn, supervisorctl, nginx) - see [here](../docs/Architecture.md) for more information on the technology stack.
* Bash shell scripts, with names of format ***script-name.sh***, that are called by the application (i.e. from within python modules).  NB. some scripts were previously run as cron jobs, but these were replaced by Router scheduler functionality).

## Config files

* Files with names of format ***filename.conf*** are all Supervisor configuration files.

* The ***gconf.py*** file is a gunicorn config file.

* ***jper_nginx*** - holds the nginx configuration for App1 linux server.

* ***etc_sudoers-d_jenkins*** - holds sudoers configuration that must be installed (manually) as a file named `/etc/sudoers.d/jenkins` and given '0440' permissions: `sudo chmod 0440  /etc/sudoers.d/jenkins`.  
***NB***. This must be installed BEFORE running Jenkins deployment jobs.

NOTE: Sample nginx configuration for the PubRouter servers can be found here: [Router Build Tools repository](https://github.com/jisc-services/oa-PubRouter-Build-Tools/tree/master/nginx). 

## Shell scripts (and cron)

### Installation

Some Files in this `deployment` directory are copied or linked to by the application installation process (performed by Jenkins).  See the `jenkins_deployment.sh` script in the project root directory.
   
#### Shell scripts called by application
Note that the Web (web or jper) application relies upon some shell scripts which it "looks" for in <code>~/.pubrouter/sh/</code> directory.  Since the Pubrouter application is run by the **jenkins** user, this means it looks in */home/jenkins/.pubrouter/sh*.

Accordingly the application installation process requires that a symlink for <code>sh</code> is set up in *~/.pubrouter* to point to the actual script location (<code>deployment/shellscripts</code> directory), which after installation (by Jenkins job) is <code>/usr/local/PubRouter/deployment/shellscripts</code>.

Thus in <code>~/.pubrouter</code> we have <code>sh -> /usr/local/PubRouter/deployment/shellscripts</code>. 

#### Shell scripts run by cron (now obsolete)
Previously some shell scripts are run by cron jobs, but these were replaced by embedded functions run by Router's scheduler.

### Cron files (deprecated)
Cron files come in pairs:
* *some-filename*.sh - this is the bash shell script that contains the code to be executed

* *some-filename*.cron - this is the companion cron command that executes the shell script at the required frequency / time of day

The installation process previously copied the `*.cron` files into the `/etc/cron.d` directory and removed the `.cron` suffix (otherwise cron ignores them).  The functionality to do this still exists in the [deployment script](../jenkins/jenkins_deployment.sh) in case there is a future need for use of cron (although ideally any new timed jobs would be incorporated into the Router scheduling system).

### Bash scripts

These are files with names ending *.sh*.

#### IMPORTANT: Executable shell-scripts

##### 1. Ensuring scripts have executable flag set
It is necessary to set the shell-script executable status in file properties (in Windows file manager):

* Right-click the file
* Select Git tab
* Check the Executable (+x) checkbox.

##### 2. If scripts need to run as sudo
If the script needs to be run with root permissions, then on each server where the script is to run you will need to create an entry in the ***/etc/sudoers.d/jenkins*** file as follows:

Add a line at the end of the file like that shown below (replacing 'YOUR-SCRIPT-NAME' with the name of your script)
<pre>
jenkins ALL = (root) NOPASSWD:/home/jenkins/.pubrouter/sh/YOUR-SCRIPT-NAME
</pre>

Note that PubRouter runs the scripts as the 'jenkins' user. The above entry indicates that the script can be run as sudo with no password.

## Gunicorn configuration

The file ***gconf.py*** is used by gunicorn.

See [here](../docs/Architecture.md) for more info on Gunicorn.
