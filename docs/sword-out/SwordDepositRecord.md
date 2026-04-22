# SwordDepositRecord

The JSON structure of the model is as follows:

```json
{
    "id": "integer", 
    "deposit_date": "2015-11-25T09:18:48Z", 
    "note_id": "integer", 
    "repo_id": "integer", 
    "metadata_status": "integer", 
    "content_status": "integer", 
    "completed_status": "integer", 
    "error_message": "string",
    "doi": "string",
    "edit_iri": "string", 
    "err_emailed": "bool"
}
```

Each of the fields is defined as laid out in the table below:

| Field            | Description                                                                                 | Datatype | Format | Allowed Values            |
|------------------|---------------------------------------------------------------------------------------------|----------| ------ |---------------------------|
| id               | Record ID                                                                                   | integer  |  |                           |
| deposit_date     | Date of this deposit                                                                        | string   | UTC ISO formatted date: YYYY-MM-DDTHH:MM:SSZ ||
| note_id          | Foreign key to notification record ID                                                       | integer  |  |                           |
| repo_id          | Foreign key to account record ID                                                            | integer  |  |                           |
| metadata_status  | Status of the metadata deposit request.                                                     | integer  |  | DEPOSITED (1), FAILED (0) |
| content_status   | Status of the content (file) deposit request.  If no binary content, this will be None.     | integer  |  | DEPOSITED (1), FAILED (0), None   |
| completed_status | Status of the "complete" request.  If no binary content, this None.                         | integer  |  | DEPOSITED (1), FAILED (0), None   |
| error_message    | Any error captured during SWORD deposit attempt                                             | string   |  |                           |
| doi              | DOI of article                                                                              | string   |  |                           |
| edit_iri         | URL to record created in repository, used to update the record -e.g. by depositing content  | string   |  |                           |
| err_emailed      | Boolean flag indicating if the error (if one exists) has been emailed to repository account | integer  |  |                           |
