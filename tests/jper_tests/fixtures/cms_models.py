"""
Code used for testing CMS (content management system).

Provides ability to create new records in cms_ctl and cms_html tables.
"""
from copy import deepcopy
from router.jper.models.admin import CmsMgtCtl, CmsHtml


CMS_CTL_RECORD = {
    "cms_type": "test-content-type",
    "sort_by": "0",
    "updated": "timestamp",
    "brief_desc": "",
    "title": "test content",
    "full_desc": "",
    "multi": True,
    "page_link": "/test/test-content-type",
    "preview_wrapper": '<div><div class="preview"></div></div>',
    "template": "<p>{field-one}</p><p>{field-two}</p>",
    "fields": [
        {
            "field": "field-one",
            "label": "Label for field-one",
            "rows": "2"
        },
        {
            "field": "field-two",
            "label": "Label for field-two",
            "rows": "2"
        },
    ]
}

CMS_HTML_RECORD = {
    "id": 1,
    "created": "timestamp",
    "updated": "timestamp",
    "cms_type": "test-content-type",
    "status": "N", # one of "N" new, "L" live, "D" deleted, "S" superseded",
    "fields": {
        "sort_value": "",
        "field-one": "Content of field-one",
        "field-two": "Content of field-two"
        }
}


class CMSFactory:

    @staticmethod
    def make_ctl_record(cms_type=None, sort_by=None, multi=True, field_names=None):
        ctl_dict = deepcopy(CMS_CTL_RECORD)
        if cms_type is None:
            cms_type = "test-content-type"
        ctl_dict["cms_type"] = cms_type
        ctl_dict["sort_by"] = sort_by
        ctl_dict["brief_desc"] = f"Brief description of {cms_type}"
        ctl_dict["full_desc"] = f"Full description of {cms_type}."
        ctl_dict["page_link"] = f"/test/{cms_type}"
        ctl_dict["multi"] = multi
        if field_names is not None:
            template = ""
            fields = []
            for field in field_names:
                template += f"<p>{{{field}}}</p>"   # Triple brackets results in string like: "<p>{field-name}</p>
                fields.append({"field": field, "label": f"Label for {field}", "rows": 2})
            ctl_dict["template"] = template
            ctl_dict["fields"] = fields
        ctl_obj = CmsMgtCtl(ctl_dict)
        ctl_obj.insert(reload=True)
        return ctl_obj.data


    @staticmethod
    def make_html_record(cms_type=None, status="N", sort="", field_names=None):
        html_rec = deepcopy(CMS_HTML_RECORD)
        if cms_type is not None:
            html_rec["cms_type"] = cms_type
        html_rec["status"] = status
        if field_names is not None:
            html_rec["fields"] = {f"{field}": f"Content of {field}" for field in field_names}
        html_rec["fields"]["sort_value"] = sort
        html_obj = CmsHtml(html_rec)
        html_obj.insert(reload=True)
        return html_obj.data
