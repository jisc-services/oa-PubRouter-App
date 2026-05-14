# Development Guidelines

## Database - access & changes

The MySQL database stores all the data used by Router (other than that contained in configuration files).  Only conventional database tables and columns are used (i.e. no use of JSON extensions) despite the fact that internally Router's data is stored as Python dictionaries and exposed (via API) as JSON objects.

Data **must always** be accessed through Classes derived from the Data Access Object (DAO) library which provides a full range of CRUD (create, read, update and delete) functions - see `octopus/modules/mysql/dao.py` (which contains detailed comments on class & function usage).  SQL queries must always be defined only in the MySQL-DAO file `src/router/shared/mysql_dao.py` - so there is a single point of reference.  This ensures that a consistent approach, based on **database cursors**, is always used - which has benefits for security, operational performance and maintainability.

The only exception would be in the use of Scripts (see the `/scripts` directory), e.g. for data migrations or one-off tasks, when the `octopus/modules/mysql/utils.py` library might be used to perform DDL operations and one-off database queries.

#### Read Queries
Retrieving data is accomplished using one of the provided DAO builtin functions defined in classes:
* `TableDAOMixin`:
  * pull()  - to retrieve a single record - either as a dict or a class object
  * pull_all() - to retrieve a full batch of records satisfying a defined query - either as dicts or class objects
* `TableDAO`:
  * pull()  - to retrieve a single record dict
  * pull_all_count() - retrieve a full batch of records (each a dict) satisfying simple SQL queries that return all record columns  
  * bespoke_pull() - retrieve full batch of records (each a raw data tuple) satisfying more complex SQL queries that return specified record columns possibly from JOINED tables.
  * scroller_obj() - provides a memory efficient scroller for retrieving a full set of records in batches using either simple or complex queries, returning data as raw data tuples, or record dict, or record class object, or a bespoke value (via a callback formatting function) 
  * reusable_scroller_obj() - as for scroller_obj(), but Scroller & associated cursors persist between successive calls  

#### Write Queries

Changes to data are accomplished using DAO functions:

* `TableDAOMixin`:
  * insert() - insert an individual record
  * update() - update an individual record
* `TableDAO`:
  * insert() - insert an individual record
  * bespoke_insert() - more complex inserts (e.g. insert multiple records using bespoke SQL query)
  * update() - update an individual record
  * bespoke_update() - more complex updates (e.g. update multiple records, possibly in several JOINED tables, using bespoke SQL query)

#### Delete Queries

Records may be deleted using DAO functions:
* `TableDAOMixin`:
  * delete() - delete individual record
* `TableDAO`:
  * delete() - delete individual record
  * delete_by_query() - more complex deleted (e.g. delete multiple records, possibly from several JOINED tables, using bespoke SQL query)
  * truncate_table() - delete ALL records in a table.


### Changes to the database
Any changes to database tables, indexes, constraints etc. **must** be made via re-usable DDL or Python release script files, so that the same changes can be implemented on all database instances (Dev, Test, UAT, Live). 

These scripts should be stored in the `scripts/release_xx.y` directory for the particular release.  

For example see:
* `scripts/release_12.4` which contains _*.sql_ DDL files and related _*.py_ files with code for migrating data.
* `scripts/Release_13.4/update_modified_notification_table.py` a python release script that (1) Creates a backup copy of the `notification` table to be altered; (2) Alters a column in the `notification` table; (3) Modifies all records to update the value stored in the altered column.

**IMPORTANT:** Any database changes **MUST** also be reflected in the file `src/router/shared/mysql_db_ddl.py` which is used by the Test programs to generate a test database that should be identical to that in Production.

### More information
For information on the database, including data-model and data table descriptions, see the [Database](Database.md) documentation page.

### Router's data access philosophy
The fundamental philosophy is to keep it simple:
* Queries are constructed in SQL
* Databae is maintained by DDL (SQL) or Python Release scripts scripts
* No need to learn another technology (such as SQLAlchemy)
* The `octopus/modules/mysql/dao.py` library was designed to seamlessly tie in with the pre-existing Data Object Class `octopus/lib/dataobj.py`, upon which all Router's objects are based.

### Why not use an ORM?
The use of SQL Alchemy was considered, but discounted for the following reasons:
* large learning-curve
* adds a fat layer of abstraction & obfuscation
* difficult to tune/optimize database queries.


## Tests

All new Router functionality must have appropriate tests created or existing tests modified.

Router test files are located in the `/tests` directory, outside the main Router `/src` library directory.

Octopus test files are located in the `octopus/tests` directory.


## Code Comments

All classes and functions should have _triple quoted_ (""") docstrings that describe:
* Purpose
* Usage (where appropriate)
* Parameters - including variable type (e.g. String / Int / Boolean / Object etc), possible values, description
* Return value - variable type, structure (particularly if a tuple is returned), description.

Within the code **in-line comments** should be used liberally to explain the purpose of any code which is complex or relies on deep understanding of Router's logic/structure; or to provide insight as to why a particular coding pattern has been adopted.  

ALWAYS put yourself in the shoes of a new Router developer, who may need to gain rapid understanding of the code - which (for good reasons) is relatively complicated in places.  

ASK YOURSELF - "if I look at this code in 5 years time will I remember why I coded it this way?".  

It's better to provide too many comments than too few. 
