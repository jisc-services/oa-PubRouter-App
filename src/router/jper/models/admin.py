"""
File contains models used for system administration functionality:
* Content management system:
    * CmsMgtCtl - Model for control CMS structure (relates to db table: cms_ctl)
    * CmsHtml = Model for CMS HTML content  (relates to db table cms_html).
"""

from router.shared.mysql_dao import CmsHtmlDAO, CmsMgtCtlDAO

class CmsMgtCtl(CmsMgtCtlDAO):
    """
    Class for control of managed content (web page content that can be amended by admin users).

    Dict:
        {
            "cms_type": "content-type-keyword (max 15 chars)",
            "sort_by": "character to sort records on (max 1 char)",
            "updated": "timestamp",
            "brief_desc": "brief description e.g. for use in select dropdown (max 80 chars)",
            "title": "title for edit panel",
            "full_desc": "full description of content type",
            "multi": True/False - whether there are multiple / single instances of content. multi: True implies 'sort' field.
            "page_link": "/... - relative URL to web page on which the content is displayed",
            "preview_wrapper": 'HTML to wrap around template for preview display - MUST contain an element with
                                class="preview" (the content to be previewed is appended to this element).'
            "template": "HTML template containing {field-name} placeholders in curly brackets"
            "fields": [
                {
                    "field": "field-name-keyword (as appearing in template above)",
                    "label": "label for text-area box that appears on form",
                    "placeholder": "Text to appear in empty input box",
                    "sample": "OPTIONAL sample text (HTML) added to empty input box (on Edit form display)",
                    "rows": number of rows for <textarea> element
                },
             ]
        }
    """
    @classmethod
    def list_cms_types(cls):
        """
        Retrieve list of content-types (for e.g. for populating dropdown list).

        :return: List of tuples (cms_type-keyword, description) sorted by `sort_by` record value.
        """
        # bespoke_pull() returns list of record tuples, each tuple contains all fields returned for a record
        # The query defined for "bspk_cms_types" returns cms_type and description fields where `sort_by` is NOT NULL
        # There are only a handful of cms_type records, so no need to use a scroller here.
        return cls.bespoke_pull(pull_name="bspk_cms_types")


class CmsHtml(CmsHtmlDAO):
    """
    Class for managed content (web page content that can be amended by admin users) which is stored in cms_html table.

    Dict:
        {
            "id": <integer>,
            "created": "timestamp",
            "updated": "timestamp",
            "cms_type": "content type (FK to cms_ctl record)",
            "status": "CHAR(1) - one of "N" new, "L" live, "D" deleted, "S" superseded",
            "fields": {
                        "sort_value": "sort value",
                        "...": "CMS content value"
                      }
        }
    Changes are performed via AJAX function calls from front-end, with record information submitted via dicts - which
    is why the majority of functions has a single dict parameter.
    """
    @staticmethod
    def new_dict_with_fields(data_dict, keep_key_list):
        return {k: data_dict[k] for k in keep_key_list}

    @classmethod
    def _pull_current_record_for_update(cls, data_dict):
        """
        Retrieve current record, validate cms_type

        :param data_dict: Dict containing at minimum:
            {
                "id": <integer>,
                "cms_type": "content type (FK to cms_ctl record)",
                ...
            }
        :return: Record Object
        """
        curr_rec = cls.pull(data_dict["id"], for_update=True, raise_if_none=True)
        if curr_rec.data["cms_type"] != data_dict["cms_type"]:
            raise ValueError(f"Specified cms_type '{data_dict['cms_type']}' does not match required type '{curr_rec.data['cms_type']}'.")
        return curr_rec


    @classmethod
    def save_and_archive_content(cls, data_dict):
        """
        If only status or sort_value has changed, then simply update the record specified by Id, otherwise if
        data fields (other than sort_value) have changed, then mark existing record as superseded and insert data_dict
        as a NEW record.

        :param data_dict: Dict containing data
            {
                "id": <integer>,
                "cms_type": "content type (FK to cms_ctl record)",
                "status": "CHAR(1) - one of "N" new, "L" live, "D" deleted, "S" superseded",
                "fields": {
                            "sort_value": "sort value",
                            "...": "CMS content value"
                          }
            }
        :return: String - "saved" (archived & inserted) | "updated" (updated)
        """
        # Retrieve existing record
        curr_rec = cls._pull_current_record_for_update(data_dict)
        data_changed = 0    # Bit indicator.  Bit 0 (value 1) == sort_value changed.  Bit 1 (value 2) == other value changed
        # See what has changed
        for k, v in curr_rec.data["fields"].items():
            if data_dict["fields"][k] != v:
                # Set bit depending on which type of value has changed
                data_changed |= (1 if k == 'sort_value' else 2)

        # If data fields changed, then need to archive existing record & create new one
        if data_changed & 2:
            curr_rec.data["status"] = "S"   # Superseded
            curr_rec.update()
            # Keep only indicated fields from data_dict, create new instance and insert record
            new_rec = cls(cls.new_dict_with_fields(data_dict, ["cms_type", "status", "fields"]))
            saved_rec = new_rec.insert()
            return "saved (& previous version archived)"
        else:
            curr_rec.data["status"] = data_dict["status"]
            if data_changed:
                curr_rec.data["fields"] = data_dict["fields"]
            curr_rec.update()
            return "updated"

    @classmethod
    def update_status(cls, data_dict):
        """
        Update content record status value only.
        :param data_dict: Dict containing data
            {
                "id": <integer>,
                "cms_type": "content type (FK to cms_ctl record)",
                "status": "CHAR(1) - one of "N" new, "L" live, "D" deleted, "S" superseded",
            }
        :return: String - indicating status that was set.
        """
        # Retrieve record for update as dict (wrap=False); raise exception if expected record not found
        curr_rec = cls._pull_current_record_for_update(data_dict)
        curr_rec.data["status"] = data_dict["status"]
        curr_rec.update()
        return {"D": "deleted", "L": "made live", "N": "made new", "S": "superseded"}.get(data_dict["status"],
                                                                                               "status UNKNOWN!")

    @classmethod
    def list_content_of_type(cls, cms_type, status=None):
        """
        Retrieve all content of particular cms_type which have specified status (None/New, Live, Superseded, Deleted).

        :param cms_type: String - Content type keyword
        :param status: None or String - Single status or concatenated string of statuses of records to return:
                            "N" (New), "L" (Live), "S" (Superseded),  "D" (Deleted) or any combination (e.g. "NL").

        :return: List of record dicts
        """
        # Retrieve recs if status is set, otherwise just return empty list
        return cls.pull_all(cms_type, status, pull_name="content_of_type", wrap=False) if status else []

