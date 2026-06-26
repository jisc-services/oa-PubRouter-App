# Miscellaneous Functionality


## Automatic Monthly Reports
At the beginning of each month Router produces a set of reports (for internal consumption), containing monthly data upto the end of the previous month, which are emailed to specified recipients (defined in system config).

Report production occurs in 2 steps:
1. Consolidate data for the previous month, and write it to database records
2. Construct CSV reports for the current year (up to the end of the last month), store on disk and email to internal recipients.

Note in _Database records_ column in table below, FK means foreign key.

| Report name   | Database records   | Details   | Notes   |
|---|---|---|---|
| Live Institution Report | DB table: _monthly_institution_stats_ <br/><br/>1 record per month per Live insitution; plus 1 record holding _unique total_ (which has _acc_id_ field set to 0).<br/><br/>Record fields:<br/> - _year_month_date_<br/> - _type_: L - live, or T - test<br/> - _acc_id_ (FK to Org _account_ record, except for record storing _unique total_ values)<br/>- _metadata_only_ count<br/> - _with_content_ count | A report covering the current year (Jan to Dec).<br/><br/>Presents one row of data for each Live institution.<br/><br/>Shows:<br/> - Institution name,<br/> - Jisc ID number,<br/> - Repository name,<br/> - Date made live,<br/> - For each month, the number of:<br/> &nbsp; - Metadata only notifications<br/> &nbsp; - Notifcations with content (article PDFs).<br/><br/>Has 2 total rows:<br/> - Grand total across all live institutions<br/> - Total unique notifications (count a notification ONCE where it matched several institutions) | Internal consumption.<br/>Emailed to:<br/> - Service manager,<br/> - Router support email address.<br/>(Defined in system config) |
| Test Institution Report | As above, but for Test institutions.   | As for Live above, but for Insitutions with Test status (no Live date).   | As above.   |
| Publisher Report   | DB table: _monthly_publisher_stats_ <br/><br/>1 record per month per publisher.<br/><br/>Record fields:<br/> - _year_month_date_<br/> - _acc_id_ (FK to Org _account_ record)<br/>- _received_ count<br/> - _matched_ count   | A report covering the current year (Jan to Dec).<br/><br/>Presents one row of data for each publisher.<br/><br/>Shows:<br/> - Publisher name<br/> - For each month:<br/> &nbsp; - total number of submissions (deposits)<br/> &nbsp; - number of submissions matched to at least one institution.<br/><br/>Has a Grand total row.   |   As above.   |
| Harvester Report   | DB table: _monthly_harvester_stats_ <br/><br/>1 record per month per harvested source.<br/><br/>Record fields:<br/> - _year_month_date_<br/> - _acc_id_ (FK to Harvester _h_webservice_ record)<br/>- _received_ count<br/> - _matched_ count   | A report covering the current year (Jan to Dec).<br/><br/>Presents one row of data for each harvester.<br/><br/>Shows:<br/> - Harvester name<br/> - For each month:<br/> &nbsp; - total number of harvested notifications<br/> &nbsp; - number of notifications matched to at least one institution.<br/><br/>Has a Grand total row.   |   As above.   |

<br/>
One additional report is produced each month, which does NOT first create a consolidated reporting record. 

| Report name   | Details   | Notes  |
|---|------|--|
| Duplicate submissions report | A report covering the previous month.<br/><br/>Lists those articles (or other publication type), identified by DOI, for which duplicate versions have been received (within the month).<br/><br/>Shows, for each duplicate article:<br/> - Number of duplicates received<br/> - Publisher name<br/> - DOI<br/> - Names of submitted files<br/> - Deposit dates<br/> - The institutions to which the articles are matched<br/> - Notification IDs<br/> - Notification metrics data string(s) - these indicate the extent to which duplicate notifications vary. |  Internal consumption.<br/>Emailed to:<br/> - Service manager,<br/> - Router support email address.<br/>(Defined in system config) |


<br/>

## Reports run from GUI

### Count of articles (& other publication types) in period 

The (admin) user selects the date range of interest.

This report is output ONLY to the screen, and shows the number of unique items (deduplicated by DOI) from publishers and harvested sources that were routed to at least one live repository account within the selected period.

It presents a table of 4 columns:
- Category of publication (Journal article, Report, Review, Book, Conference output, Other, Preprint, Unknown)
- Number (of items) containing a PDF 
- Number that were metadata only
- Total items.

### Ad-hoc duplicate submissions

This produces the same report as the automatic monthly _Duplicate submissions report_ (see table above), BUT over a date range specified by the (admin) user. 

The results are displayed as a table on screen, with an option to download the data as a CSV file.

### Miscellaneous reports

| Title   | Description   | Notes   |
|---|---|-----------------------------------------|
| Analyse providers structured affiliation usage | Scan ALL notifications (3 months worth) &amp; report on providers use of structured affiliations.   | Report run as background job & emailed. |
| Analyse affiliations for overpopulated institution (org) elements |  Scan ALL notifications (3 months worth) &amp; report on providers use of 'institution' (org) element in structured affiliations. | Report run as background job & emailed. |
| Analyse various 'type' values in notifications | Scan ALL notifications (3 months worth) &amp; list the 'type' values of various metadata items. | Report run as background job & emailed. |


<br/>

## Matching parameter downloads

Matching parameters can be downloaded in a variety of ways.

From individual Repository Organisation accounts, the organisation's matching parameters can be downloaded as self-contained CSV or JSON files (by an administrator).

Administrators can also download matching parameters for ALL accounts into single output files as described here.

| Title                                                                  | Description                                                                                                                                                | Notes                  |
|------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------|------------------------|
| List matching parameters for all repository account                    | For all repository accounts, list matching parameters except ORCIDs & Grant-numbers for which counts are given.<br>Parameters are separated by '  ~  '.    | CSV file for downlad.  |
| List matching parameters (with newlines) for all repository accounts   | For all repository accounts, list matching parameters except ORCIDs & Grant-numbers for which counts are given.<br>Each parameter is listed on a new line. | CSV file for downlad.  |
| Detailed matching parameters as JSON for all repository accounts       | Outputs matching parameter records (full detail) for all repository accounts in 1 JSON format file. Convenient for full details in one place.              | JSON file for downlad. |
| Zip file of JSON & CSV matching parameters for each repository account |Outputs a Zip containing separate CSV & JSON matching parameters files (suitable for uploading) for each repository account.| Zip file for download. |
| Zip file of detailed JSON matching parameters for each repository account |Outputs a Zip containing separate JSON detailed matching parameters files (NOT for uploading) for each repository account.|  Zip file for download  |

