-- Change the `proc_name` values of certain entries:
--    * Adhoc-report --> Adhoc-Report
--    * Delete-data --> Delete-Data

update metrics set proc_name = 'Delete-Data' where proc_name = 'Delete-data';
update metrics set proc_name = 'Adhoc-Report' where proc_name = 'Adhoc-report';
