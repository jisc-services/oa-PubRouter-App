"""
JPER service initialise module, run at application startup.

The main initialise() function is run when the app is started every time

NOTE:
    This file used to contain the code to create an Admin user which is now in shared/create_admin_acc.py
    It didn't make sense to call it every time JPER is started.  Instead, a new script 'scripts/create_admin_user.py'
    has been created so that new deployments of Router can be "seeded" with an Admin account.

    This file has been retained in case in future there is some JPER specific code to be run at initialisation. IF
    that is the case, then in 'jper/app.py' the commented out line:  `# update_init(app, 'shared.initialise')` should
    be reinstated.
"""
pass

