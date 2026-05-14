"""
Functions and classes associated with Adding / Editing User Details.

NOTE: to disable a field, use this construct:  field_name = StringField('Label', render_kw={"disabled":True})

"""
import re
from flask_login import current_user
from wtforms import Form, validators, SelectField, RadioField, StringField, IntegerField, \
    TextAreaField, BooleanField, ValidationError
from wtforms.fields import URLField, EmailField
from router.shared.models.account import AccOrg, AccUser
from router.shared.models.doi_register import dup_choices_tuple_list, select_tuple_arr_formatter


class AddFullStops:
    """
    Bespoke translation class that ensures that internal messages always end with a full stop.
    """
    def gettext(self, string):
        return string if string.endswith('.') else string + '.'

    def ngettext(self, singular, plural, n):
        return self.gettext(plural if n > 1 else singular)


class MultiEmailField(TextAreaField):
    """
    Special version of TextAreaField that accepts Email addresses, each separated by a space(s) or comma or semicolon.
    """
    email_validator_regex = re.compile(r'^[-.\w]+@([-\w]+\.[-.\w]+)$', re.IGNORECASE)
    email_split_regex = re.compile(r'[,; ]+')

    def __init__(self, *args, **kwargs):
        self.email_list = []
        self.num_bad = 0
        super(MultiEmailField, self).__init__(*args, **kwargs)

    def validate(self, form, extra_validators=()):
        self.email_list = []
        self.num_bad = 0
        # Basic field level validation
        ok = super(MultiEmailField, self).validate(form, extra_validators=extra_validators)

        if ok:
            email_string = self.data.strip(" ,;\n\r\t")
            if email_string:
                bad_emails = []
                # Split input string on comma, semicolon or space
                emails_list = self.email_split_regex.split(email_string)
                for email in emails_list:
                    if not self.email_validator_regex.match(email):
                        bad_emails.append(f"'{email}'")

                if bad_emails:
                    self.num_bad = len(bad_emails)
                    template = "Email {} has an{}" if self.num_bad == 1 else "Emails {} have{}s"
                    self.errors.append(template.format(", ".join(bad_emails), " invalid format"))
                    ok = False
                else:
                    self.email_list = emails_list
        return ok


class AccForm(Form):
    """
    Provide special handling for disabled fields.

    Override the wtforms Form class to ensure that internally generated error messages always have fullstops,
    as there are inconsistencies (some messages have full-stops and others don't).
    """

    def __init__(self, formdata=None, obj=None, prefix='', data=None, meta=None, disable_fields=None, acc_id=None, **kwargs):
        super(AccForm, self).__init__(formdata=formdata, obj=obj, prefix=prefix, data=data, meta=meta, **kwargs)

        self.all_fields_disabled = disable_fields is True
        self.disabled_field_names_set = self._set_disable_flag_on_fields(disable_fields)
        self.acc_id = acc_id

    def _get_translations(self):
        return AddFullStops()

    def _set_disable_flag_on_fields(self, disable_fields):
        if isinstance(disable_fields, list):
            for name, field in self._fields.items():
                setattr(field.flags, "is_disabled", name in disable_fields)
            disabled_field_names_set = set(disable_fields)
        else:
            val = disable_fields is True
            for field in self._fields.values():
                setattr(field.flags, "is_disabled", val)
            disabled_field_names_set = set(self._fields.keys()) if disable_fields else None
        return disabled_field_names_set

    def any_field_changed(self):
        for field in self._fields.values():
            if field.data != field.object_data:
                return True
        return False

    def field_changed(self, field_name):
        """
        Indicates if field has changed value
        :param field_name:
        :return: Boolean True - has changed; False - no change
        """
        field = self._fields.get(field_name)
        if field is None:
            raise ValueError(f"Form field '{field_name}' not found.")
        return field.data != field.object_data

    def validate(self, extra_validators=None):
        """
        Set disabled field values (which the form never returns)

        Then validate the form inputs.

        :return: True if all is OK, False if validation failed
        """
        def _set_data(field):
            _data = field.object_data  # Original value
            field.data = _data
            field.raw_data = [_data]

        if self.all_fields_disabled:
            for _field in self._fields.values():
                _set_data(_field)
            return True     # No validation needed
        else:
            if self.disabled_field_names_set:
                # Set the data & raw_data values (which are never returned when a Form is submitted)
                for field_name in self.disabled_field_names_set:
                    _set_data(self._fields[field_name])
            # Normal form validation
            return super(AccForm, self).validate(extra_validators=extra_validators)

    def all_errors_list(self):
        """
        Return list of all errors occuring in form
        :return: List of errors
        """
        all_errors = []
        for err_list in self.errors.values():
            all_errors += err_list
        return all_errors

    def error_summary(self, sep="; "):
        """
        Return summary of errors
        :param sep: String - Separator character(s)
        :return: string summarising all errors
        """
        return sep.join(self.all_errors_list())


class RepoSettingsForm(AccForm):
    # A complete tuple may be deleted in order to affect the GUI drop-down options.
    # However, for any tuple that remains, the first value must not be modified as it impacts code logic,
    # but the second value which is displayed may be modified.
    repo_sw_choices = [
        ('other', 'Other'),
        ('dspace-v5', 'DSpace v5.x'),
        ('dspace-v6', 'DSpace v6.x'),
        ('eprints', 'Eprints'),
        ('elements-eprints', 'Symplectic Elements via Eprints'),
        ('elements-dspace', 'Symplectic Elements via DSpace'),
        ('haplo', 'Haplo (via API)'),
        ('pure', 'Pure (via API)'),
        ('worktribe', 'Worktribe (via API)'),
        ## UNCOMMENT THIS to provide a "native" XML option which does a simple conversion of Router's datamodel from JSON to XML
        # ('native', 'Native / Esploro')
    ]
    xml_format_choices = [
        ('', 'None', ''),
        ('eprints', 'Eprints Native', 'Router sends Eprints standard XML'),
        ('eprints-rioxx-2', 'Eprints RIOXXplus v2', 'Router sends Eprints RIOXXplus XML v2'),
        ('eprints-rioxx', 'Eprints RIOXXplus v1 (old)', 'Router sends Eprints RIOXXplus XML v1'),
        ('dspace', 'DSpace Native', 'Router sends DSpace standard XML (based on dcterms)'),
        ('dspace-rioxx', 'DSpace RIOXX', 'Router sends DSpace XML enhanced with rioxxterms and other elements'),
        ('native', 'Router Native', 'For repositories that ingest Router default metadata XML'),
    ]

    repository_name = StringField('Repository name', validators=[validators.InputRequired()])
    repository_url = URLField('Repository URL', validators=[validators.InputRequired(), validators.URL()])
    repository_software = SelectField('Repo / CRIS software', choices=repo_sw_choices, default='other')
    # This is hidden field (in `Manage connection settings` panel)
    packaging = SelectField('Packaging preferences', choices=[], default='http://purl.org/net/sword/package/SimpleZip', validate_choice=False)
    xml_format = SelectField('Repository config', choices=select_tuple_arr_formatter(xml_format_choices, "ls"), default='')
    # Target queue field only shows up depending on xml_format being some form of eprints
    target_queue = SelectField('Deposit location',
                               choices=select_tuple_arr_formatter(
                                   [("manage", "Manage Deposit", "Deposits will appear in the 'Manage Deposits' queue"),
                                    ("review", "Review Queue", "Deposits will appear in the 'Review' queue")],
                                   "ls"),
                               default="manage")
    sword_username = StringField('Sword username', description="repository SWORD username")
    sword_password = StringField('Sword password', description="repository SWORD password")
    sword_collection = URLField('Sword collection URL',
                                description="full URL of collection endpoint",
                                validators=[validators.Optional(), validators.URL()])

    eprints_dspace_native_regex = re.compile(r'(?:eprints|dspace|native)')

    def validate_it(self, ac_is_live):
        """
        Validate the Repository settings (this is not called `validate` as requires non-standard parameter)
        :param ac_is_live: Boolean - True: account is Live; False: account is Test
        :return: True if all is OK, False if validation failed
        """
        # Basic field level validation
        validation_status = super(RepoSettingsForm, self).validate()

        # Additional validation - conditional on field values

        # Repository software is indicated to be one of our supported repos, so SWORD details should be filled in
        repo_sw = self.repository_software.data
        if self.eprints_dspace_native_regex.search(repo_sw):
            xml_format = self.xml_format.data
            if not xml_format:
                self.xml_format.errors.append("Configuration must be specified")
            elif "eprints" in repo_sw and "eprints" not in xml_format:
                self.xml_format.errors.append("Repository selected above is Eprints")
            elif "dspace" in repo_sw and "dspace" not in xml_format:
                self.xml_format.errors.append("Repository selected above is Dspace")
            elif "native" in repo_sw and "native" not in xml_format:
                self.xml_format.errors.append("Repository selected above is Native")

            if not self.sword_username.data:
                self.sword_username.errors.append("Required field")
            if not self.sword_password.data:
                self.sword_password.errors.append("Required field")
            if not self.sword_collection.data:
                self.sword_collection.errors.append("Required field")
        elif ac_is_live:   # Must be a CRIS, so SWORD details should NOT be filled in if Account is Live
            err_msg = "Field should be empty as using API & account is Live"
            if self.xml_format.data != "":
                self.xml_format.errors.append("You are using a CRIS & account is Live so this should be None")
            if self.sword_username.data:
                self.sword_username.errors.append(err_msg)
            if self.sword_password.data:
                self.sword_password.errors.append(err_msg)
            if self.sword_collection.data:
                self.sword_collection.errors.append(err_msg)
        if self.xml_format.errors or self.sword_username.errors or self.sword_password.errors or self.sword_collection.errors:
            validation_status = False

        # If we got this far then additional validation was all OK, so return result of basic validation
        return validation_status


class RepoDuplicatesForm(AccForm):
    """
    Form for entering / maintaining information related to Handling Duplicates
    """
    dups_level_pub = SelectField("From publishers",
                             choices=dup_choices_tuple_list,
                             default=0,
                             coerce=int)
    dups_level_harv = SelectField("From secondary sources",
                             choices=dup_choices_tuple_list,
                             default=0,
                             coerce=int)
    ### TODO: INCLUDE in FUTURE RELEASE if Send-duplicates-by-email functionality is wanted
    # dups_emails = MultiEmailField("Email addresses for duplicate notifications",
    #                                    validators=[validators.optional()],
    #                                    render_kw={"rows": "6",
    #                                               "title": "Separate email addresses by space, comma or semicolon"},
    #                                    description="Email addresses to which duplicate notifications will be sent. Separate by space, comma or semicolon.")
    # dups_meta_format = SelectField("Metadata format",
    #                               choices=[("txt", "Text (tabular)"), ("xml", "XML"), ("json", "JSON")],
    #                               default="txt")


class PubSettingsForm(AccForm):
    """
    Form for publisher specific settings - Embargo duration, Default licence details, Peer reviewed indicator
    """
    embargo_duration = IntegerField('Default embargo duration (months)',
                                    # Allow empty field or must have a number between 0 and 120
                                    [validators.Optional(),
                                     validators.NumberRange(min=0,
                                                            max=120,
                                                            message='Please enter number of months (integer value).')],
                                    description="Number of months (integer value)")
    license_url = URLField('Licence URL',
                           # Allow empty field or must have a URL
                           [validators.Optional(), validators.URL()],
                           description="URL of post-embargo licence")
    license_title = TextAreaField('Licence title',
                                  [validators.Optional(), validators.Length(min=10, max=200)],
                                  description="Description of licence (up to 200 characters)")
    license_type = StringField('Licence type', description="Example: 'CC BY-NC-ND'")
    license_version = StringField('Licence version', description="Licence version number, such as '3.0'")
    peer_reviewed = BooleanField("All articles peer reviewed")

    def validate(self, extra_validators=None):
        """
        Validate the Publisher license & embargo settings

        :return: True if all is OK, False if validation failed
        """

        def _field_empty(field):
            return field.raw_data and field.raw_data[0] == ''

        # Basic field level validation
        validation_status = super(PubSettingsForm, self).validate()

        # Additional validation - conditional on field values

        # IF both the required fields are empty, then all fields should be empty
        if _field_empty(self.embargo_duration) and _field_empty(self.license_url):
            # If any other field is NOT empty
            if not (_field_empty(self.license_title) and _field_empty(self.license_type) and
                    _field_empty(self.license_version)):
                validation_status = False
                err_msg = 'Required - enter a value or delete other entries.'
                self.embargo_duration.errors.append(err_msg)
                self.license_url.errors.append(err_msg)

        # Either Embargo or URL (or both fields) are not empty, in which case both are required
        elif _field_empty(self.embargo_duration):
            self.embargo_duration.errors.append('You must enter an Embargo period as well as a Licence URL.')
            validation_status = False

        elif _field_empty(self.license_url):
            self.license_url.errors.append('You must enter a Licence URL as well as an Embargo period.')
            validation_status = False

        # If we got this far then additional validation was all OK, so return result of basic validation
        return validation_status


class PubTestingForm(AccForm):
    """
    Form for entering / maintaining information related to publisher testing
    """
    # Publisher agreement options
    test_type_choices = [
        # ('value', 'Displayed text' in dropdown) -
        # Note the values 'u' and 'b' equate to UPON_PUB and BEFORE_PUT values in jper/pub_testing.py
        ('u', 'AM or VoR upon publication'),
        ('b', 'AM before publication'),
    ]

    in_test = BooleanField("Testing")
    # First test_type_choices value is default)
    test_type = SelectField("Agreement type", choices=test_type_choices, default=test_type_choices[0][0])
    test_report_emails = MultiEmailField("Email addresses for results",
                                       validators=[validators.Optional(), validators.Length(max=2000)],
                                       render_kw={"rows": "6",
                                                  "title": "Separate email addresses by space, comma or semicolon"},
                                       description="Emails to which error reports will be sent. Separate by space, comma or semicolon.")

    test_start = StringField("", render_kw={"aria_label": "Testing started date"})  # Shows start-date string
    start_checkbox = BooleanField("Testing started")

    test_end = StringField("", render_kw={"aria_label": "Testing ended date"})  # Shows end-date string
    end_checkbox = BooleanField("Testing ended")

    # Summary info - fields are always protected
    last_error = StringField("Last failure")
    last_ok = StringField("Last success")
    num_err_tests = IntegerField("Total failures")
    num_ok_tests = IntegerField("Total successes")
    num_ok_since_last_err = IntegerField("Successes since last failure")
    route_note_checkbox = BooleanField("Route notifications")


class PubReportsForm(AccForm):
    """
    Form for entering / maintaining information related to publisher reports
    """
    report_format_choices = [
        # ("value", "Displayed text" in dropdown) -
        ("", "No report"),
        ("C", "1 row per DOI, institution names semicolon separated"),
        ("N", "1 row per DOI, institution names semicolon + newline separated"),
        ("S", "1 row per institution (all columns populated)"),
        ("B", "1 row per institution, other data not repeated"),
    ]
    # First report_format_choices value is default)
    report_format = SelectField("Report format", choices=report_format_choices, default=report_format_choices[0][0])
    report_emails = MultiEmailField("Recipient email addresses",
                                       validators=[validators.Optional(), validators.Length(max=2000)],
                                       render_kw={"rows": "6",
                                                  "title": "Separate email addresses by space, comma or semicolon"},
                                       description="Emails to which the report will be sent. Separate by space, comma or semicolon.")


class PasswordUserForm(Form):
    """
    Set password form
    """
    password = StringField('Password', render_kw={"autocomplete":"off"})
    password_verify = StringField('Verify password', render_kw={"autocomplete":"off"})

    def validate_password(self, field):
        pwd = field.data
        err_msgs = []
        length = len(pwd)
        if length > 0:
            if length < 12:
                err_msgs.append("Password length must be at least 12 characters.")

            for pattern in (r"\d", r"[A-Z]", r"[a-z]", r"[\"¬`£$%^&*()_\-+={}[\]:;@'~#|\\<>?,./!]"):
                if re.search(pattern, pwd) is None:
                    err_msgs.append("Password must contain upper & lower case characters, and 1 or more digits & symbols.")
                    break

            if re.search(r"^sha1", pwd):
                err_msgs.append("Password cannot start with 'sha1'.")

            if err_msgs:
                raise ValidationError(" ".join(err_msgs))

        return True

    def validate_password_verify(self, field):
        if field.data != self.password.data:
            raise ValidationError("The passwords don't match.")
        return True


class UserDetailsForm(AccForm, PasswordUserForm):
    """
    Form used for Individual Users
    """
    def __init__(self, *args, **kwargs):
        super(UserDetailsForm, self).__init__(*args, **kwargs)
        self.username_is_email = None
        self.curr_user_org_acc = current_user.acc_org

    def verify_username(self, username):
        # If a different account exists in the system with this username then Error
        user_acc = AccUser.pull_by_username(username.data)
        if user_acc is not None and user_acc.id != self.acc_id:
            raise ValidationError("Username already taken.")
        return True

    def check_email(self, email):
        """
        For non-JiscAdmin users, an email is required. However, Jisc admin users may supply a non-email value
        @param email: 
        @return: 
        """
        # Check that a valid email is entered, HOWEVER allow Jisc Admin users to enter a Non-email string.

        validate_email = validators.Email()
        try:
            validate_email(self, email)
            self.username_is_email = True
        except Exception as e:
            if self.curr_user_org_acc.is_super:
                self.username_is_email = False  # Don't raise error, but indicate username is Not an email
            else:
                self.username_is_email = None   # Indicates a "Bad email" error was raised
                raise e
            
        return True

    def check_if_user_email_reqd(self, user_email):
        """
        A contact email is only wanted where Username is NOT an email (& is allowed to be such)
        @param user_email: User's Contact email field
        @return:
        """
        if self.username_is_email:
            if user_email.data:     # Contact email entered
                raise ValidationError("Contact email not allowed where username is an email.")
        elif self.username_is_email is False:
           return validators.InputRequired()(self, user_email)

        return validators.Optional()(self, user_email)  # As nothing entered, Optional() stops further validation:


    def set_role_code_choices(self, required="SRAJD"):
        _options_dict = {
            "S": "Standard User",
            "R": "Read-only User",
            "A": "Organisation Admin",
            "J": "YOUR-ORG Admin",
            "D": "YOUR-ORG Developer",
            "K": "API Key User"
        }
        _role_code_options = [(k, _options_dict[k]) for k in list(required)]

        self.role_code.choices = _role_code_options
        self.role_code.default = _role_code_options[0][0]
        # return _role_code_options


    # Username should normally be an email address, but for Jisc Admins an exception is made.
    username = StringField("Username", [validators.InputRequired(), check_email, verify_username, validators.Length(min=2, max=80)],
                           description="Organisation email required")

    # This field is only available to (Jisc) Admin Org account users
    user_email = EmailField("Contact email", [check_if_user_email_reqd, validators.Email()],
                            description="Required if username is not an email")

    surname = StringField("Surname", [validators.InputRequired(), validators.Length(min=2, max=100)])

    forename = StringField("Forename", [validators.InputRequired(), validators.Length(min=1, max=100)])

    org_role = StringField("Job title", [validators.Length(max=100)],
                           description="User's role in organisation")

    # IMPORTANT: The choices will be set dynamically in the View function
    role_code = SelectField("User type", choices=[], validators=[validators.InputRequired()])

    user_note = TextAreaField("Note", [validators.Length(max=7000)], render_kw={"rows": "3"})

    direct_login = BooleanField("Direct login")

    ## These fields are always protected
    last_success = StringField("Last successful login", render_kw={"disabled": True})
    last_failed = StringField("Last failed login", render_kw={"disabled": True})
    num_failed = IntegerField("Failed attempts", render_kw={"disabled": True})


class OrgDataForm(AccForm):
    """
    Form for basic Organisation Details (Org name, Note, Contact email, Technical contact emails)
    """
    def verify_contact_email(self, email_field):
        org_acc = AccOrg.pull_by_contact_email(email_field.data)
        # If a different account exists in the system with same contact email then error
        if org_acc is not None and org_acc.id != self.acc_id:
            raise ValidationError('Contact email already in use.')
        return True

    organisation_name = StringField('Organisation Name',
                                    [validators.InputRequired(), validators.Length(min=2, max=100)])
    note = TextAreaField('Note', [validators.Length(max=5000)], render_kw={"rows": "5"})

    contact_email = EmailField('Contact Email',
                               [validators.InputRequired(), validators.Email(), verify_contact_email],
                               description="An organisation email address.")

    tech_contact_emails = MultiEmailField("Technical Contact Emails",
                                       validators=[validators.Optional(), validators.Length(max=2000)],
                                       render_kw={"rows": "3",
                                                  "title": "Separate email addresses by space, comma or semicolon"},
                                       description="Email addresses to which automated errors will be sent. Separate by space, comma or semicolon.")


class AddOrgForm(OrgDataForm, UserDetailsForm):
    """
    Form for NEW ORGANISATION USER & INITIAL ORG ADMIN USER
    """
    # Includes the fields from OrgDataForm
    role = RadioField(
        'Account type',
        choices=[('publisher', 'Publisher'), ('repository', 'Repository'), ('admin', 'Admin')]
    )


class OrgIdentifiersForm(AccForm):
    """
    AccForm for identifiers - as it's admin only best to give it a form for itself.
    """
    jisc_id = StringField('Jisc ID', description="Institution name")
    jisc_id_name = StringField()

    core_id = StringField('CORE Repository ID', description="Institution repository name")
    core_id_name = StringField()


class MatchSettingsForm(AccForm):
    """
    Form for match settings - currently has maximum age of article
    """
    # Has to be optional as otherwise null will not be allowed
    pub_years = IntegerField(
        'Maximum age (years)',
        [validators.Optional(), validators.NumberRange(1, 100)],
        description="Number of years (optional)"
    )


class CompareMatchParamsForm(Form):
    """
    Select field used on Compare Match Params form
    """
    prev_param = SelectField('Archived versions', choices=[], coerce=int, description="Previous match parameters")

    def __init__(self, formdata=None, obj=None, prefix='', data=None, meta=None, archived_versions=None, selected=None, **kwargs):
        super(CompareMatchParamsForm, self).__init__(formdata=formdata, obj=obj, prefix=prefix, data=data, meta=meta, **kwargs)
        self.set_choices(archived_versions or [], selected)
        
    def set_choices(self, archived_versions, selected):
        self.prev_param.choices = [(pkid, f"{archived.strftime('%d/%m/%Y %H:%M:%S')}{' – RegEx' if has_regex else ''} – (pkid {pkid})") for pkid, archived, has_regex in archived_versions ]
        self.prev_param.data = selected
        
        
