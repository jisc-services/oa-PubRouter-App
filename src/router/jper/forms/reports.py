from wtforms import Form, SelectField  ##, IntegerField, DateField, FileField, StringField, TextAreaField

class MiscReportScriptsForm(Form):
    # report_info dict is used below and also in views\reports.py & run_misc_reports.html
    # The tuple has following 5 elements:
    #   0 - Report summary (displayed as select field option)
    #   1 - Report description (added as title attribute to select field option)
    #   2 - Further information
    #   3 - Report name
    #   4 - Output filename for script (could contain '{}' placeholders if script can fill them)
    #   5 - Boolean flag indicates if report is run as a Batch (True) or Online (False) job
    report_info = {
        "aff_analysis": (
            "Analyse providers structured affiliation usage",
            "Scan ALL notifications (3 months worth) & report on providers use of structured affiliations.",
            "This report is run as a background job as it can take minutes to produce. The report CSV file will be emailed to you on completion.",
            "Provider structured affiliation usage",
            "affiliation_analysis_{}.csv",
            True    # Batch report
        ),
        "aff_org_analysis": (
            "Analyse affiliations for overpopulated institution (org) elements",
            "Scan ALL notifications (3 months worth) & report on providers use of 'institution' (org) element in structured affiliations.",
            "This report is run as a background job as it can take minutes to produce. The report CSV file will be emailed to you on completion.",
            "Provider affiliation institution (org) element usage",
            "aff_org_usage_{}.csv",
            True  # Batch report
        ),
        "note_analysis": (
            "Analyse various 'type' values in notifications",
            "Scan ALL notifications (3 months worth) & list the 'type' values of various metadata items.",
            "This report is run as a background job as it can take minutes to produce. The report text file will be emailed to you on completion.",
            "Notification metadata 'type' values",
            "note_type_values_analysis_{}.txt",
            True  # Batch report
        ),
        ## Example of an online report - this & 2 other entries have now moved to forms\account.py (with some modifications)
        # "matching_params": (
        #     "List matching parameters for all repository accounts",
        #     "Summarise matching parameters for all repository accounts, except ORCIDs & Grant-numbers for which counts are given.  Parameters are separated by '  ~  '.  ",
        #     "This report is provided as a CSV file for download.",
        #     "All accounts matching parameters (CSV)",
        #     "all_matching_parameters.csv",
        #     False  # Online report
        # ),
    }
    report_selector = SelectField(
        "Report script",
        choices=[("", "Choose one")] + [(k, v[0], {"title": v[1], "data-info": v[2]}) for k, v in report_info.items()]
    )
