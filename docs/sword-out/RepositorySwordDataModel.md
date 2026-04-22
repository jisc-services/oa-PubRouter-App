# Repository SWORD data

The JSON structure of the model is as follows:

```json
{
    "username" : "username for Router to authenticate with the repository",
    "password" : "password for the router to authenticate with the repository",
    "collection" : "url for deposit collection to receive content from the router",
    "last_updated" : "Timestamp "%Y-%m-%dT%H:%M:%SZ" when this record was last updated",
    "last_deposit_date" : "Datetime '%Y-%m-%dT%H:%M:%SZ' of analysis date of the last notification that was successfully deposited",
    "last_note_id": "Id of notification last successfully deposited",
    "retries" : "Number of attempted deposits",
    "last_tried" : "Timestamp of last attempted failed deposit or None if deposit is successful"
}
```
Note that the actual SWORD account `status` value is stored at a higher level as part of the AccOrg structure that contains the above structure.  
