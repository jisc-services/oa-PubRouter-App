Put command line scripts in this directory.

All scripts SHOULD have an informative comment at the top of the file that summarises:
 * Script purpose
 * Calling convention, including description of any parameters.

Scripts related to particular releases - e.g. which perform database changes and the like - must be placed in a sub-directory named: ***Release_xx.yy***.

Scripts with (likely) one-off usage should be placed in sub-directory ***z_misc_one_off***.

Pure SQL scripts should be placed in sub-directory: ***MySQL_queries***.

