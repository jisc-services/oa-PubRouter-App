from wtforms import Form, IntegerField, DateField, SelectField, FileField, StringField, TextAreaField


class IdentifierUploadForm(Form):

    choices = SelectField(
        "Identifier type",
        choices=[("JISC", "JISC"), ("CORE", "CORE")],
        default="JISC"
    )
    csv_file = FileField("CSV File")


class JsonRecordForm(Form):

    dao_name = SelectField(
        "Record type",
        choices=[
            ("AccOrgDAO", "Organisation Account"),
            ("AccUserDAO", "User Account"),
            ("AccNotesEmailsDAO", "Emails/Notes"),
            ("AccBulkEmailDAO", "Bulk Email"),
            ("AccRepoMatchParamsDAO", "Acc Match Params (acc_id)"),
            ("AccRepoMatchParamsArchivedDAO", "Acc Match Params Archived (pkid)"),
            ("RoutedNotificationDAO", "Routed Notification"),
            ("UnroutedNotificationDAO", "Unrouted Notification"),
            ("HarvestedUnroutedNotificationDAO", "Harvested Unrouted Notification"),
            ("NotificationAccountDAO", "Notification Account (K: note_id, acc_id)"),
            ("ContentLogDAO", "Content Log"),
            ("CmsMgtCtlDAO", "CMS Control"),
            ("CmsHtmlDAO", "CMS Html"),
            ("DoiRegisterDAO", "DOI Register"),
            ("IdentifierDAO", "Institution identifier (K: type, value)"),
            ("MatchProvenanceDAO", "Match Provenance (K: note_id, repo_id)" ),
            ("PubDepositRecordDAO", "Pub Deposit Record"),
            ("PubTestRecordDAO", "Pub Test Record"),
            ("SwordDepositRecordDAO", "Sword Deposit Record"),
            ("HarvWebServiceRecordDAO", "Harv Web Service Record"),
            ("HarvErrorRecordDAO", "Harv Error Record"),
            ("HarvHistoryRecordDAO", "Harv History Record"),
            ("MonthlyInstitutionStatsDAO", "Monthly Institution Stats (K: yyyy-mm-01, type: L/T, acc_id)"),
            ("MonthlyPublisherStatsDAO", "Monthly Publisher Stats (K: yyyy-mm-01, acc_id)"),
            ("MonthlyHarvesterStatsDAO", "Monthly Harvester Stats (K: yyyy-mm-01, acc_id)")
        ]
    )
    rec_id = StringField("Id")
    json_data = TextAreaField('JSON record', render_kw={"rows": "12"})


class MetricDisplayForm(Form):

    from_date = DateField("Show from")
    to_date = DateField("To")
    proc_name = SelectField(
        "Show for process",
        choices=[
            ("", "All"),    # Show ALL metrics records
            ("Move-FTP", "Move-FTP"),
            ("Process-FTP", "Process-FTP"),
            ("Route-Publisher", "Route-Publisher"),
            ("Route-Harvested", "Route-Harvested"),
            ("SWORD-out", "SWORD-Out"),
            ("Harvest", "Harvest"),
            ("Delete-Data", "Delete-Data"),
            ("Delete-Files", "Delete-Files"),
            ("Monthly", "Monthly"),
            ("Adhoc-Report", "Adhoc-Report"),
            ("MAX-ALL", "*MAX Duration for All*"),  # Special case - show Maximum duration for each proc_name
        ],
        default=""
    )
    min_count = IntegerField("Minimum count", default=0)
