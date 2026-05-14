# Contents of 'shellscripts' directory

This directory holds BASHBash shell scripts, with names of format ***script-name.sh***, that are either called by the application (i.e. from within python modules) or run as cron jobs

## Shell scripts called by application
Note that the Web (web or jper) application relies upon some shell scripts which it "looks" for in <code>~/.pubrouter/sh/</code> directory.  Since the Pubrouter application is run by the **jenkins** user, this means it looks in */home/jenkins/.pubrouter/sh*.

The application runs these scripts with 'root' permissions, which means these scripts also need to be defined in the ***/etc/sudoers.d/jenkins*** file as follows:

Add a line at the end of the file like that shown below (replacing 'YOUR-SCRIPT-NAME' with the name of your script)
<pre>
jenkins ALL = (root) NOPASSWD:/home/jenkins/.pubrouter/sh/YOUR-SCRIPT-NAME
</pre>

Note that PubRouter runs the scripts as the 'jenkins' user. The above entry indicates that the script can be run as sudo with no password.

Accordingly the application installation process requires that a symlink for <code>sh</code> is set up in *~/.pubrouter* to point to the actual script location (<code>deployment/shellscripts</code> directory), which after installation (by Jenkins job) is <code>/usr/local/PubRouter/deployment/shellscripts/</code>.

Thus in <code>~/.pubrouter</code> we have <code>sh -> /usr/local/PubRouter/deployment/shellscripts</code>. 
