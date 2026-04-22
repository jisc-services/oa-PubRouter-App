#
#   Functionality associated with automated testing of new Publishers submissions to PubRouter.
#
import re
from datetime import datetime
from logging import CRITICAL, ERROR, WARNING, INFO, DEBUG
from flask import current_app
# Import all the error levels CRITICAL, ... because although not used here, they are imported elsewhere.
from octopus.modules.logger.logger import init_logger
from octopus.lib.data import dictionary_get_dot_notation, dict_to_json_compressed_base64, dictionary_get
from octopus.lib.mail import MailMsg, MailAccount
from router.jper.models.publisher import PubTestRecord

# Regex checking string for creative commons URLs
CC_CHECKER_REGEX = r'^https?:\/\/creativecommons\.org\/(?:publicdomain\/zero\/1.0|licenses\/by(?:-nc)?(?:-nd|-sa)?\/[1-4]\.[0])(?:\/|\/legalcode)?$'
regex_check_creativecommons = re.compile(CC_CHECKER_REGEX)

# Regex encodes problematic strings - Ignores case: (?i) - as defined here: https://jisc365.sharepoint.com/:w:/r/sites/PublicationsRouter/Technical/Report%20specs%20etc/2024-04%20Trapping%20overpopn%20org%20element%20in%20affiliations.docx?d=wbe633c298b0d4dad90074a7ac7b99581&csf=1&web=1&e=rooNT8
PROBLEM_ORG_REGEX = r'(?i)(?:\n|Also at|Building|c\/o|C(?:ampus|ent(?:er|re)|hair|onsultant)|D(?:ep(?:t|artment)|i(?:rectorate|vision))|F(?:ac(?:ility|ulty)|loor)|Group|House|In(?:itiative|stitute)|L(?:aboratory|ibrar)|Pro(?:fessor|gram)|Road|Se(?:ction|rvice d)|Team|Unit)'
regex_check_problem_org_values = re.compile(PROBLEM_ORG_REGEX)
# String contains "University" but NOT "University College"  - Ignores case: (?i)
UNI_NOT_UNI_COLLEGE_REGEX = r'(?i)(?:University)(?! College)'
regex_univ_not_univ_college = re.compile(UNI_NOT_UNI_COLLEGE_REGEX)
# String contains "School" or "College" - Ignores case: (?i)
SCHOOL_OR_COLLEGE_REGEX = r'(?i)(?:School|College)'
regex_school_or_college = re.compile(SCHOOL_OR_COLLEGE_REGEX)


OPEN_LICENCE_SUBSTR = 'www.nationalarchives.gov.uk/doc/open-government-licence'

UPON_PUB = "u"
BEFORE_PUB = "b"

VALIDATE_VALUE = 1
VALIDATE_VALUE_LIST = 2
VALIDATE_DICT_LIST = 3

ROOT_EL = "~"   # Special key value indicating a root element


def validate_aff_org_value(org_str):
    """
    Validate affiliation <org> element to check if it appears to contain more than just Organisation name.

    (NOTE: This function is located here & not within the following class as it is also used by a report).
    :param org_str: String - Organisation value
    :return: None or brief string indicating problematic content of org_str
    """
    issue = None
    # If more than 1 comma in string
    if org_str.count(",") > 1:
        issue = "more than 1 comma"
    else:
        #  if Org string contains a problematic string
        match = regex_check_problem_org_values.search(org_str)
        if match:
            issue = f"\"{match[0]}\""
        else:
            # Org string contains complex problematic string University and College or School
            if regex_univ_not_univ_college.search(org_str):
                match = regex_school_or_college.search(org_str)
                if match:
                    issue = f"\"University\" & \"{match[0]}\""
    return issue


class DictValidator:
    def __init__(self):
        self.validation_results = {}

    @staticmethod
    def add_entry(result_dict, key, value):
        if result_dict:
            try:
                result_dict[key].add(value)
            except KeyError:
                # First entry for key - create list [count-
                result_dict[key] = {value}

    @staticmethod
    def update_entry(result_dict, key, value_list):
        if result_dict:
            try:
                result_dict[key].update(value_list)
            except KeyError:
                # First entry for key - create list [count-
                result_dict[key] = set(value_list)

    @staticmethod
    def field_value(field, key):
        """
        Returns field or field + "." + key depending on whether key indicates Root element
        :param field: field value
        :param key: key value
        :return: string
        """
        return field if key == ROOT_EL else f"{field}.{key}"

    @staticmethod
    def format_list(string_list, sq_brackets=False, item_template="'{}'"):
        """
        Format a list into a string like "['something', 'or', 'other']" or "'something', 'or', 'other'"
        :param string_list: List of strings
        :param sq_brackets: Boolean - True: Surround string with square brackets; False: No square brackets
        :param item_template: String - template for each list item
        :return: Formatted string
        """
        string = ", ".join([item_template.format(string_) for string_ in string_list])
        return f"[{string}]" if sq_brackets else string

    def get_or_add_result_dict(self, result_dict, field_id, obj_list_len=0):
        """
        Add a child result dict to the result_dict children dict if it doesn't already exist.
        Return either the existing or new child result dict.

        :param result_dict: parent result_dict
        :param field_id: id of the field
        :param obj_list_len: Length of object list

        :return: new child result dict
        """
        parent_field_id = result_dict.get("fld")
        full_field_id = f"{parent_field_id}.{field_id}" if parent_field_id else field_id
        try:
            # Get result structure for current field if it exists (if not a KeyError will arise)
            child_dict = self.validation_results[full_field_id]
            if obj_list_len:
                child_dict["count"] += obj_list_len
        except KeyError:
            # Create and add new result dict
            child_dict = {
                "fld": full_field_id,
                "count": obj_list_len,  # Number of items in list
                # "stars": 0,  # Count of `star-value` (if specified) that have been found
                # "miss": set(),  # Stores missing key values
                # "empty": set(),  # Stores empty key values
                # "d_miss": set(),  # Stores missing key values for desirable fields
                # "d_empty": set(),  # Stores empty key values for desirable fields
                # "o_miss": set(),  # Stores missing key values for optional fields
                # "o_empty": set(),  # Stores empty key values for optional fields
                # "unexp": set(),  # Stores unexpected keys
                # "invalid": {},  # Dict of tuples, field-name: (set(invalid-values), [validation-list])
                # "irreg": {},  # Dict of tuples, field-name: (set(undesirable-values), [preferred-values-list])
                # "errors": set(),  # Errors
                # "issues": set(),  # Issues (warnings)
                # "info": set()  # Information
            }
            # If we have a multi-value list or its parent is multi-value
            if obj_list_len > 1 or (parent_field_id and result_dict.get("multi")):
                child_dict["multi"] = True
            self.validation_results[full_field_id] = child_dict

        return child_dict

    @staticmethod
    def add_invalid_or_irregular(result_dict, result_key, key, value, valid_list):
        """
        Adds entry to result_dict["invalid"] or result_dict["irreg"] which each hold a dictionary, keyed by field-name
        which holds a tuple (set(bad-value, ...), [validation-list])
        :param result_dict:
        :param result_key: Key to result dict - either "invalid" or "irreg"
        :param key: Key of field that was validated
        :param value: Value that failed validation
        :param valid_list: List of valid values
        :return:
        """
        try:
            result_dict_entry = result_dict[result_key]
            existing_tuple = result_dict_entry.get(key)
            if existing_tuple:
                # existing tuple has structure: [set(bad-values), [validation-list]]
                # Add value to existing set of bad values
                existing_tuple[0].add(value)
            else:
                # first time a bad value is found for this key, so add the key and list containing
                # count, set of bad values and validation list
                result_dict_entry[key] = ({value}, valid_list)
        except KeyError:
            result_dict[result_key] = {key: ({value}, valid_list)}

    def validate_value(self, result_dict, key, value, validator, required):
        """

        :param result_dict: Dict - holds control information and validation results
        :param key: String - key of value being validated (or "~" if validating a `root` field)
        :param value: Value being processed
        :param validator: Either None, or a List-of-allowed-values, or a validation-function-name
        :param required: - Character - One of: "m"=Mandatory, "d"=Desirable, "o"=Optional
        :return: Value validated
        """
        map_reqd_to_key = {
            "m": ("empty", "miss"),  # Mandatory
            "d": ("d_empty", "d_miss"),  # Desirable
            "o": ("o_empty", "o_miss")  # Optional
        }
        # if value is simple string remove any surrounding white space
        if isinstance(value, str):
            value = value.strip()

        if not value:
            # Add key to "miss", "d_miss" or "o_miss" set; OR "empty", "d_empty" or "o_empty" set
            # depending on whether value is None or otherwise empty
            ix = 1 if value is None else 0
            self.add_entry(result_dict, map_reqd_to_key[required][ix], key)

        # We have a non-empty value, so validate it if there is a validator
        elif validator is not None:
            # if we have a list of allowed values
            if isinstance(validator, list):
                # If invalid value, need to store details
                if value not in validator:
                    self.add_invalid_or_irregular(result_dict, "invalid", key, value, validator)

            # If we have a validation function
            elif callable(validator):
                validator(result_dict, value, key)
        return value

    def validate_dict_list(self, result_dict, obj_list, essential_keys=None, desirable_keys=None, optional_keys=None,
                           star_dict=None, obj_validator_fn=None):
        """
        Validates a list of objects. For each object:
            * checks if its essential, desirable and optional keys are present and
            * whether values are missing or invalid (not in an allowed-values list); also
            * checks if unexpected keys are present.
            * finally, performs bespoke validation with `obj_validator_fn` function (if present);
            * optionally, counts if particular `star value` is present in any of the objects within the list.

        :param result_dict: Dict - holds control information and validation results
        :param obj_list: List of object to check
        :param essential_keys: List or dict of essential keys - these must all be present
        :param desirable_keys: List or dict of desirable keys - absence raises a Warning
        :param optional_keys: list or dict of optional keys - absence raises no warning
        :param star_dict: Optional dict containing key for which value is to be checked (must be an essential key)
        :param obj_validator_fn: Optional validation function with arguments (result_dict, object_value)
        :return: Nothing but may update result_dict.
        """

        def _create_master_list_and_dict(list_or_dict):
            """
            Create a new list of object keys from `list_or_dict` either by copying the list (if that is what it is)
            or from its keys if it is a dict; Also creates a new validation dict by copying `list_or_dict` if it is
            a dict, or if it is a list, then sets as empty dict.

            :param list_or_dict: A List or a dict.
            :return: Tuple: keys-list, validation-dict
            """
            # If `list_or_dict` is a List
            if isinstance(list_or_dict, list):
                return list_or_dict.copy(), {}
            # If it is a dict
            elif isinstance(list_or_dict, dict):
                return list(list_or_dict.keys()), list_or_dict.copy()  # Note: shallow copy
            else:
                return [], {}

        essential_keys_master, essential_validation_dict = _create_master_list_and_dict(essential_keys)
        desirable_keys_master, desirable_validation_dict = _create_master_list_and_dict(desirable_keys)
        optional_keys_master, optional_validation_dict = _create_master_list_and_dict(optional_keys)

        star_count = result_dict.get("stars", 0) if star_dict else 0
        for obj in obj_list:
            # Make copies of essential & desirable keys arrays as we will be removing items
            cpy_essential_keys = essential_keys_master.copy()
            cpy_desirable_keys = desirable_keys_master.copy()
            cpy_optional_keys = optional_keys_master.copy()

            # Iterate over all keys in the object, perform validation on each
            for obj_key in obj.keys():
                # Perform validation depending on whether key is essential / desirable / optional
                if obj_key in cpy_essential_keys:
                    cpy_essential_keys.remove(obj_key)
                    val = self.validate(result_dict, obj_key, obj[obj_key], essential_validation_dict.get(obj_key), "m")
                elif obj_key in cpy_desirable_keys:
                    cpy_desirable_keys.remove(obj_key)
                    val = self.validate(result_dict, obj_key, obj[obj_key], desirable_validation_dict.get(obj_key), "d")
                elif obj_key in optional_keys_master:
                    cpy_optional_keys.remove(obj_key)
                    val = self.validate(result_dict, obj_key, obj[obj_key], optional_validation_dict.get(obj_key), "o")
                else:
                    val = None
                    self.add_entry(result_dict, "unexp", obj_key)

                # if value not empty and a star_dict is specified, and current key is of interest
                if val and star_dict:
                    # and obj_key in star_dict:
                    try:
                        star_val = star_dict[obj_key]
                        # if star value is wild-card OR current value matches star value
                        if star_val == "*" or star_val == val:
                            star_count += 1
                    except KeyError:
                        pass
            # Any keys remaining in any of the keys lists were not found in the object, so record as missing
            if cpy_essential_keys:
                self.update_entry(result_dict, "miss", cpy_essential_keys)
            if cpy_desirable_keys:
                self.update_entry(result_dict, "d_miss", cpy_desirable_keys)
            if cpy_optional_keys:
                self.update_entry(result_dict, "o_miss", cpy_optional_keys)

            # Call object bespoke validation function if wanted
            if obj_validator_fn:
                obj_validator_fn(result_dict, obj)

        if star_dict:
            result_dict["stars"] = star_count

    def validate(self, result_dict, key, value, validator, required, root=False):
        """
        Perform validation of passed value, using content of validator. Function may be called recursively.

        Variables root ---> True = new result_dict
        Validator is dict or not --> dict, validate object, new result_dict
        :param result_dict: Dict of results - Is UPDATED by this function call
        :param key: String - key of value or object being validated - can be a "dot.string"
        :param value: Various - Value being validated, can be simple scalar value, or list of values or list of dicts or dict.
        :param validator: Various - None, or List, or Dict or Function (determines how to validate the passed `value`
        :param required: Char - one of 'o' (optional), 'd' (desirable), 'm' (mandatory)
        :param root: Boolean - True: this "root" function call (i.e. not recursed into); False: Recursive call
        :return: validated value is returned ONLY if value-validation is done, otherwise None is returned
        """
        # print(f"\n++ Validate\n    Key= {key}\n    Required= {required}\n    Result-dict= {result_dict}\n    Validator= {validator}\n    Value= {value}")
        list_len = 0
        # validate_value is the default validation (even for dicts, unless a validation-dict is provided)
        validation_reqd = VALIDATE_VALUE
        if isinstance(value, dict):
            # if value is a dict and validator is a dict then we will use validation function validate_dict_list
            # otherwise we do simple value validation of the dict
            if isinstance(validator, dict):
                value = [value]  # validate_dict_list requires a list of dicts
                validation_reqd = VALIDATE_DICT_LIST
        elif isinstance(value, list):
            list_len = len(value)
            if list_len > 0:
                # we have a list of dicts and the validator is a dict, then validate_dict_list is used
                # otherwise simple value validation is done
                if isinstance(value[0], dict):
                    if isinstance(validator, dict):
                        validation_reqd = VALIDATE_DICT_LIST
                # not a list of dicts, so use list value validation
                else:
                    validation_reqd = VALIDATE_VALUE_LIST

        if validation_reqd == VALIDATE_DICT_LIST:
            self.validate_dict_list(self.get_or_add_result_dict(result_dict, key, list_len),
                                    value,
                                    **validator)
        else:
            if root:
                result_dict = self.get_or_add_result_dict(result_dict, key, list_len)
                key = ROOT_EL

            if validation_reqd == VALIDATE_VALUE_LIST:
                for val in value:
                    self.validate_value(result_dict, key, val, validator, required)
            else:
                # Value is returned
                return self.validate_value(result_dict, key, value, validator, required)

        return None

    def root_validate(self, key, value, validator, required):
        self.validate(self.validation_results, key, value, validator, required, root=True)

    @classmethod
    def process_result_dict_and_generate_messages(cls, result_dict):
        """
        Generate messages based on content of sets of missing, empty or unexpected field names, or set of invalid
        values.
        Example:
            "missing optional keys: 'some', 'key'; & empty value for optional key: 'another'; & unexpected keys: \
               'bad', 'badder' in at least one of the array elements"
        :param result_dict: Dict - holds control information and validation results
        :return: Tuple of 3 Strings (error_snippet, issue_snippet, invalid_snippet)
        """
        _snippet_map = [
            # (SERIOUSNESS, QUALIFIER, (2-TEMPLATES-tuple), [list-of-2-element-tuples])
            ("errors", "", ("{a}", "{a} {q}field{s}: {f}"), [
                # KEY-to-result_dict, ADJECTIVE-to-use
                ("miss", "missing"),
                ("empty", "empty"),
                ("unexp", "unexpected")
                ]
            ),
            ("issues", "desirable ", ("{a} ({q}field)", "{a} {q}field{s}: {f}"), [
                ("d_miss", "missing"),
                ("d_empty", "empty")
                ]
            ),
            ("info", "optional ", ("{a} ({q}field)", "{a} {q}field{s}: {f}"), [
                ("o_miss", "missing"),
                ("o_empty", "empty")
                ]
            )
        ]
        # print(f"\n--Fld= {result_dict['fld']}, {result_dict}")
        among_str = " among the array elements" if result_dict.get("multi") else ""
        for seriousness, qualifier, templates, tuple_list in _snippet_map:
            snippets = []
            is_has = "has"
            for key, adjective in tuple_list:
                set_ = result_dict.get(key)
                if set_:
                    set_ = list(set_)
                    if set_[0] == ROOT_EL:
                        is_has = "is"
                        snippets.append(templates[0].format(a=adjective, q=qualifier))
                    else:
                        snippets.append(templates[1].format(a=adjective,
                                                            q=qualifier,
                                                            s="s" if len(set_) > 1 else "",
                                                            f=cls.format_list(set_, item_template="«{}»")
                                                            ))
                    # print(f"---Degree = {seriousness}, Root= {set_[0] == ROOT_EL}({is_has}), Tmplt={templates[0 if set_[0] == ROOT_EL else 1]}, Key= {key}, Adjective= {adjective}, Qual= {qualifier}, LenSet= {len(set_)}, Set= {set_}")

            if snippets:
                cls.add_entry(result_dict, seriousness,
                              f"«{result_dict['fld']}» {is_has} {'; & '.join(snippets)}{among_str}")
                # print(f"--- «{result_dict['fld']}» {is_has} {'; & '.join(snippets)}{among_str}")
        for result_key, seriousness, template in (
            ("invalid", "errors", "«{}» has invalid value{}: {}{} - allowed values are: {}"),
            ("irreg", "issues", "«{}» has irregular value{}: {}{} - preferred values are: {}")
        ):
            # If some problem values found, create appropriate messages
            for key, (bad_vals_set, allowed_list) in result_dict.get(result_key, {}).items():
                err = template.format(
                    cls.field_value(result_dict["fld"], key),
                    "s" if len(bad_vals_set) > 1 else "",
                    cls.format_list(bad_vals_set),
                    among_str,
                    cls.format_list(allowed_list, sq_brackets=True)
                )
                cls.add_entry(result_dict, seriousness, err)

    def generate_errors_issues_info_from_results_dict(self):
        """
        Generate error or issue (less serious) messages which are added to the results_dict.
        :return: Nothing, but may update results_dicts in self.validation_results
        """
        for result_dict in self.validation_results.values():
            self.process_result_dict_and_generate_messages(result_dict)

    def log_errors_issues_info_from_results_dict(self, log):
        """
        Recurse over the results dict and output messages to log.
        :param log: Function - logger
        :return: Tuple (Error-count, Issue-count, Info-count)
        """
        counts = {}
        for key, log_level in (("errors", ERROR), ("issues", WARNING), ("info", INFO)):
            num = 0
            for result_dict in self.validation_results.values():
                for msg in result_dict.get(key, []):
                    log(log_level, msg)
                    num += 1
            counts[key] = num
        return counts["errors"], counts["issues"], counts["info"]


def init_pub_testing(acc=None, route=None, init_mail=False):
    """
    Initialise  a PubTesting (publisher testing) object, parameter optional.

    :param acc: Publisher account object - the account whose deposits are currently being processed
    :param route: Route by which notifications are deposited: "api" or "ftp"
    :param init_mail: Boolean - True: initialise MailMsg, False: do nothing

    :return: PubTesting object
    """
    PubTesting.init_pub_testing_class(init_mail)
    return PubTesting(acc=acc, route=route)


class PubTesting:
    mail_account = None
    jisc_emails_dict = None
    normal_logger = None
    test_logger = None

    @classmethod
    def init_pub_testing_class(cls, init_mail=False):
        if cls.normal_logger is None:
            cls.normal_logger = current_app.logger
            _config = current_app.config
            # Create a log specifically for recording details for publishers undergoing testing
            cls.test_logger = init_logger(name="pub_test",
                                          log_level=_config.get("LOGLEVEL", INFO),
                                          log_file=_config.get("PUB_TEST_LOG"),
                                          flexi_cutover=WARNING)
        if init_mail and cls.mail_account is None:
            cls.mail_account = MailAccount()
            cls.jisc_emails_dict = current_app.config.get("PUB_TEST_EMAIL_ADDR")
            cls.normal_logger.log(DEBUG,
                                  "PubTesting email initialised. Jisc emails dict: " + str(cls.jisc_emails_dict))

    def __init__(self, acc=None, route=None):
        """
        :param acc: Publisher account object
        :param route: Route by which notifications are deposited: "api" or "ftp"
        """
        self.acc = acc
        self.route = route
        if self.acc is None:
            self.pub_data = None
            self.test_active = False
            self.type = None
        else:
            self.pub_data = self.acc.publisher_data
            self.test_active = self.pub_data.in_test
            self.type = self.pub_data.test_type     #  Before or Upon publication

        self.new_submission()

    def set_filename(self, filename):
        self.filename = filename
        if self.test_active and filename:
            self.log(INFO, f"Validating submission file: '{filename}'")

    def new_submission(self, filename=None):
        """
        Initialisation related to a new submission
        :param filename: String - name of file being processed
        :return:
        """
        self.errors = []
        self.issues = []
        self.doi = None
        self.set_filename(filename)
        self.compressed_json = None

    def is_active(self):
        return self.test_active

    def not_active(self):
        return not self.test_active

    def num_errors(self):
        return len(self.errors)

    def num_issues(self):
        return len(self.issues)

    def finalise_pub_acc(self, is_ok, test_rec_id):
        """
        Finalise the publisher account record fpr this submission.
        Also, send results email
        :param is_ok: Boolean - True: no errors; False: Errors
        :param test_rec_id: String - ID of record holding test results
        :return: nothing
        """
        if self.test_active:
            self.pub_data.update_test_dates_and_stats(is_ok, datetime.today())
            self.acc.update()

            # Email test report (if email is initialised)
            self.mail_test_report(is_ok, test_rec_id)

    def create_test_record_and_finalise_autotest(self, err_msg=None):
        if self.test_active:
            try:
                if err_msg:
                    self.errors.append(err_msg)
                ok = len(self.errors) == 0
                test_record = PubTestRecord({
                    "pub_id": self.acc.id,
                    "route": self.route,
                    "fname": self.filename,
                    "doi": self.doi or None,  # Convert "" to None
                    "valid": ok,
                    "errors": self.errors,
                    "issues": self.issues,
                    "json_comp": self.compressed_json
                })
                test_record.insert()
                self.finalise_pub_acc(ok, test_record.id)
            except Exception as e:
                # Output msg to both logs
                msg = "PubTesting UNEXPECTED exception in create_test_record_and_finalise_autotest(): " + repr(e)
                self.normal_logger.critical(msg, exc_info=True)
                self.test_logger.critical(msg)
                raise e

    def log(self, level, msg, *args, prefix="", suffix="", save=True, **kwargs):
        """
        If publisher is in test mode, then log error and save to database,
        Otherwise simply log error to normal log.

        :param level: Integer - Debug level (one of: CRITICAL, ERROR, WARNING, INFO, DEBUG)
        :param msg: String - Basic message to log (with prefix & suffix added) and store (for eventual saving in db).
        :param args: Optional arguments that get inserted into msg if it contains string place-holders
        :param prefix: Prefix to add before the basic message (see `msg` above)
        :param suffix: Suffix to add after the basic message (see `msg` above)
        :param save: Whether to add `msg` to self.errors or self.issues (& ultimately save in `pub_test` data table)
        :param kwargs: Possible values passed to logging
        :return: nothing
        """
        log_msg = prefix + msg + suffix

        # If log level exceeds INFO then save as either an error or an issue
        if save and level > INFO:
            if level > WARNING:
                self.errors.append(msg)
            else:
                self.issues.append(msg)

        if self.test_active:
            self.test_logger.log(level, log_msg, *args, **kwargs)
        else:
            self.normal_logger.log(level, log_msg, *args, **kwargs)

    def logger(self):
        """
        Return either the Test Logger or the Normal Logger depending on whether the publisher is in test-mode
        :return: logger object (either standard or test-logger)
        """
        return self.test_logger if self.test_active else self.normal_logger

    def mail_test_report(self, is_ok, test_rec_id):
        """
        Email results of the test
        :param is_ok: Boolean - True: Success or False: Errors
        :param test_rec_id: String - ID of record holding test results
        :return:
        """
        # Bail out if email not initialised
        if self.mail_account is None:
            return

        email_addrs = self.pub_data.test_emails
        bcc_addrs = self.jisc_emails_dict.get(is_ok)

        # Target email addresses exist
        if email_addrs or bcc_addrs:
            file_and_doi = ""
            if self.filename:
                file_and_doi = f"File: {self.filename}"
            if self.doi:
                file_and_doi += f"{', ' if file_and_doi else ''}DOI: {self.doi}"

            subject = "{} - Test result for {} submission{}{} - {} errors, {} issues".format(
                self.acc.org_name,
                self.route.upper(),
                " - " if file_and_doi else "",
                file_and_doi,
                self.num_errors(),
                self.num_issues()
            )
            email = MailMsg(subject,
                            "mail/pub_test.html",
                            # Note that passing self.acc directly to MailMsg doesn't work because it is a LocalProxy,
                            # so have to pass pub_id, and api_key separately
                            pub_uuid=self.acc.uuid,
                            rec_id=test_rec_id,
                            api_key=self.acc.api_key,
                            file_and_doi=file_and_doi,
                            errors=self.errors,
                            issues=self.issues,
                            route=self.route)
            self.mail_account.send_mail(email_addrs, bcc=bcc_addrs, msg_obj=email)

    @staticmethod
    def get_doi_from_note_dict(notification):
        """
        Extract DOI value from notification dictionary if it exists
        :param notification: Notification dict
        :return: String DOI value or None
        """
        try:
            for id_dict in notification["metadata"]["article"]["identifier"]:
                if id_dict["type"] == "doi":
                    return id_dict["id"].lower()
        except KeyError:
            pass
        return None

    def validate_metadata(self, note_dict):
        """
        Validate submitted metadata, ensuring that key fields are present and raising errors and warnings appropriately.

        :param note_dict: Notification data dict
        :return: Tuple (Error-count, Issue-count, Info-count)
        """

        def _validate_article_identifier(result_dict, id_list, key):
            """
            Validate article identifiers list - may create error entries in result_dict.
            :param result_dict: Dict - holds control information and validation results
            :param id_list: List of article identifiers
            :param key: String - key of value being validated (or "~" if validating a `root` field)
            :return: Nothing, but may update error_list
            """
            dv.validate_dict_list(result_dict, id_list, essential_keys=["type", "id"], star_dict={"type": "doi"})
            num_doi_found = result_dict["stars"]
            if num_doi_found == 0:
                DictValidator.add_entry(result_dict, "errors",
                             f"The «{result_dict['fld']}» array must include one DOI (i.e. a «type» value of 'doi')"
                             )
            elif num_doi_found > 1:
                DictValidator.add_entry(result_dict, "errors",
                             f"The «{result_dict['fld']}» array had {num_doi_found} DOIs, but only 1 is allowed"
                             )

        def __validate_auth_contrib(result_dict, author_dict_list, validation_dict, auth_or_contrib):
            """
            Validate the content Author / Contributor struct.  Note that different rules apply (passed via
            validation_dict)
            {
                "type" : "<Type of contribution author>",
                "name" : {
                    "firstname" : "<author first name>",
                    "surname" : "<author surname>",
                    "fullname" : "<author name>",
                    "suffix" : "<Qualifiers that follow a persons name Sr. Jr. III, 3rd>"
                },
                "organisation_name" : "<Name of organisation if author is an organisation >",
                "identifier" : [{
                        "type" : "orcid",
                        "id" : "<author's orcid>"
                    }, {
                        "type" : "email",
                        "id" : "<author's email address>"
                    }],
                "affiliations": [ {
                        "identifier" : [{
                            "type" : "ISNI",
                            "id" : "<institution ISNI Id>"
                        }, {
                            "type" : "ROR",
                            "id" : "<institution ROR Id>"
                        }],
                        "org": "<Organisation name> or field absent (*)",
                        "dept": "<Org division/dept> or field absent (*)",
                        "street": "<Street> or field absent",
                        "city": "<City> or field absent",
                        "state": "<State> or field absent",
                        "postcode": "<Post code> or field absent",
                        "country": "<Country> or field absent",
                        "country_code": "<Country code> or field absent",
                        "raw": "<Unstructured affilation> or absent",
                    ] }
            }
            This ENCLOSURE uses `dv` from outer scope.

            :param result_dict: Dict - holds control information and validation results
            :param author_dict_list: List of authors
            :param validation_dict: Dict of validation rules to apply
            :param auth_or_contrib: String - "author" or "contributor"
            :return:
            """
            def _validate_org_name(result_dict, auth_dict):
                """
                Check that if there is no firstname & lastname then there IS an organisation name.

                This ENCLOSURE uses `auth_or_contrib` from outer scope.

                :param result_dict: Dict - holds control information and validation results
                :param auth_dict: Author object (as shown above)
                :return:
                """
                name_dict = auth_dict.get("name", {})
                surname = name_dict.get("surname")
                forename = name_dict.get("firstname")
                # Both first & last name are missing
                if not forename and not surname:
                    org_name = auth_dict.get("organisation_name")
                    if not org_name:
                        DictValidator.add_entry(result_dict, "errors",
                                     "«{}» must include both «name.firstname» & «name.surname» or an «organisation_name», but all are missing or empty{}".format(
                                         result_dict["fld"],
                                         f" for at least one {auth_or_contrib}" if result_dict.get("multi") else ""
                                         )
                                     )

            # Insert validation function for Org Name into the validation_dict
            validation_dict["obj_validator_fn"] = _validate_org_name
            # Validate list of author-dicts
            dv.validate_dict_list(result_dict, author_dict_list, **validation_dict)

        def _validate_contributors(result_dict, contrib_dict_list, key):
            """
            Validate list of contributors.
            :param result_dict: Dict - holds control information and validation results
            :param contrib_dict_list: List of authors
            :param key: String - key of value being validated (or "~" if validating a `root` field)
            :return:
            """
            validation_dict = {
                "essential_keys": {"type": None  # Contributors can have any `type`
                                   },
                "desirable_keys": {"identifier": {"essential_keys": ["type", "id"]}
                                   },
                # Note that organisation_name and name are validated by
                "optional_keys": {
                    "organisation_name": None,
                    "name": {"essential_keys": ["firstname", "surname"],
                             "optional_keys": ["fullname", "suffix"]},
                    "affiliations": {
                        "desirable_keys": {
                          "org": None,
                          "street": None,
                          "city": None,
                          "country": None,
                          "postcode": None,
                          "identifier": {"essential_keys": ["type", "id"]}
                        },
                        "optional_keys": ["dept", "state", "country_code", "raw"]
                    }
                }
            }
            __validate_auth_contrib(result_dict, contrib_dict_list, validation_dict, "contributor")

        def _validate_author_type(result_dict, auth_type, key):
            """
            Confirm that author-type has value containing "author" or "corresp". If not record as "irreg" or
            "invalid" value depending on actual value
            :param result_dict: Dict - holds control information and validation results
            :param auth_type: String - the author type value
            :param key: String - key of value being validated (or "~" if validating a `root` field)
            :return:
            """
            preferred = ["author", "corresp"]
            if auth_type not in preferred:
                # Author-type contains word "author" - this is an Issue as will still be processed OK
                if "author" in auth_type:
                    DictValidator.add_invalid_or_irregular(result_dict, "irreg", key, auth_type, preferred)
                else:
                    DictValidator.add_invalid_or_irregular(result_dict, "invalid", key, auth_type, preferred)

        def _validate_aff_org(result_dict, org_str, key):
            """
            Validate affiliation <org> value - check to see if it contains potentially problematic string values
            :param result_dict: Dict - holds control information and validation results
            :param org_str: String - Organisation value
            :param key: String - key of value being validated (or "~" if validating a `root` field)
            :return:
            """
            issue = validate_aff_org_value(org_str)
            if issue:
                result_dict["stars"] = result_dict.get("stars", 0) + 1    # Count of questionable <org> elements
                DictValidator.add_entry(result_dict, "issues",
                                        f"«{result_dict['fld']}.{key}» may be overpopulated: \"{org_str}\" (contains {issue})")

        def _validate_authors(result_dict, author_dict_list, key):
            """
            Validate list of authors, including their affiliations.

            This ENCLOSURE uses `dv` (dict validator instance) from outer scope.

            :param result_dict: Dict - holds control information and validation results
            :param author_dict_list: List of authors
            :param key: String - key of value being validated (or "~" if validating a `root` field)
            :return:
            """
            validation_dict = {
                "essential_keys": {
                    "type": _validate_author_type,
                    "affiliations": {
                        "essential_keys": {
                           "org": _validate_aff_org,   # NB. affiliations results_dict["stars"] counts questionable orgs
                           "city": None,
                           "country": None,
                        },
                        "desirable_keys": {
                            "dept": None,
                            "street": None,
                            "postcode": None,
                            "country_code": None,
                            "identifier": {"essential_keys": ["type", "id"]}
                        },
                        "optional_keys": ["state", "raw"]
                    }
                },
                "desirable_keys": {"identifier": {"essential_keys": ["type", "id"],
                                                  "star_dict": {"type": "orcid"}}
                                   },
                "optional_keys": {"organisation_name": None,
                                  "name": {"essential_keys": ["firstname", "surname"],
                                           "optional_keys": ["fullname", "suffix"]}
                                  },
                "star_dict": {"type": "corresp"}
            }
            __validate_auth_contrib(result_dict, author_dict_list, validation_dict, "author")

            # Check if "corresp" was found in any author `type` field
            if result_dict["stars"] == 0:
                DictValidator.add_entry(result_dict, "errors",
                                        f"The list of «{result_dict['fld']}» objects must include one with a "
                                        f"«type» value of 'corresp' (indicating corresponding author)"
                                        )

            num_authors = result_dict["count"]
            # Check if any ORCID ids found
            num_orcid = dictionary_get(dv.validation_results, f"{result_dict['fld']}.identifier", "stars", default=0)
            if num_orcid == 0:
                DictValidator.add_entry(
                    result_dict,
                    "errors",
                    f"In the «{result_dict['fld']}» array, 0 of the {num_authors} authors has an ORCID "
                    f"specified (in an «identifier» element); at least one and ideally all authors should have an ORCID specified"
                    )

            # If num ORCIDs less than number of authors
            elif num_orcid < num_authors:
                have_has = "have" if num_orcid > 1 else "has"
                DictValidator.add_entry(
                    result_dict,
                    "issues",
                    f"In the «{result_dict['fld']}» array, {num_orcid} of the {num_authors} authors {have_has}"
                    f" an ORCID specified (in an «identifier» element), ideally all authors would have this"
                    )

            # Check if any affiliation <org> elements were problematic
            aff_result_dict = dv.validation_results.get(f"{result_dict['fld']}.affiliations", {})
            org_issue_count = aff_result_dict.get("stars")
            if org_issue_count:
                if org_issue_count > 1:
                    s = "s"
                    have_has = "have"
                else:
                    s = ""
                    have_has = "has an"
                DictValidator.add_entry(
                    result_dict,
                    "issues",
                    f"In the «{result_dict['fld']}» array, {org_issue_count} of the {aff_result_dict['count']} "
                    f"affiliations (from {num_authors} authors) {have_has} «org» value{s} that may contain more than the institution name. Affiliation address elements, including department & organisation names, should each be tagged separately"
                    )

        def _validate_date(result_dict, ymd_date_string, key):
            """
            Confirm a date is of form "YYYY-MM-DD".
            :param result_dict: Dict - holds control information and validation results
            :param ymd_date_string: Date, expected to be of form "YYYY-MM-DD"
            :param key: String - key of value being validated (or "~" if validating a `root` field)

            :return:
            """
            if ymd_date_string:
                try:
                    datetime.strptime(ymd_date_string, "%Y-%m-%d")
                except Exception:
                    DictValidator.add_entry(
                        result_dict,
                        "errors",
                        "In «{}» an invalid date '{}' was found (required format is: YYYY-MM-DD)".format(
                            DictValidator.field_value(result_dict["fld"], key), ymd_date_string)
                    )

        def _validate_pub_date(result_dict, date_dict, key):
            """
            This ENCLOSURE uses `dv` (dict validator instance) from outer scope.

            "publication_date" : {
                "publication_format" : "<Format of publication (print, electronic)>",
                "date" : "<date>", /* yyyy-mm-dd format*/
                "year" : "year":"<year>" /* yyyy format */
                "month" : "month":"<month>" /* mm format */
                "day" : "day":"<day>" /* dd format */
                "season" : "<Season of publication (for example, Spring, Third Quarter).>"
            },

            :param result_dict: Dict - holds control information and validation results
            :param date_dict: Date being validated
            :param key: String - key of value being validated (or "~" if validating a `root` field)

            :return:
            """
            def _validate_date_dict(result_dict, date_dict):
                lookup = [("Year", "YYYY", "%Y"), ("Month", "MM", "%m"), ("Day", "DD", "%d")]

                yyyy_mm_dd_str = date_dict.get("date")
                date_parts = [date_dict.get("year"), date_dict.get("month"), date_dict.get("day")]
                ix = 9
                if yyyy_mm_dd_str:
                    for ix, date_format in enumerate(["%Y-%m-%d", "%Y-%m", "%Y"]):
                        try:
                            datetime.strptime(yyyy_mm_dd_str, date_format)
                            # If not the full date i.e. `ix != 0`
                            if ix:
                                DictValidator.add_entry(
                                    result_dict,
                                    "issues",
                                    "In «{}» a partial date '{}' was provided; a full date (YYYY-MM-DD) is preferred"
                                    " if possible".format(DictValidator.field_value(result_dict["fld"], key),
                                                          yyyy_mm_dd_str))
                            break  # Date is valid - so break
                        except Exception:
                            ix = 9

                    if ix == 9:
                        DictValidator.add_entry(
                            result_dict,
                            "errors",
                            "In «{}» an invalid date '{}' was found (YYYY-MM-DD, YYYY-MM or YYYY are acceptable"
                            " formats)".format(DictValidator.field_value(result_dict["fld"], key), yyyy_mm_dd_str)
                        )
                    else:
                        # Full date validated OK, so now check the component parts against individual year, month, day
                        split_date_parts = yyyy_mm_dd_str.split("-")
                        for ix, part in enumerate(split_date_parts):
                            if part != date_parts[ix]:
                                DictValidator.add_entry(
                                    result_dict,
                                    "errors",
                                    "In «{}» the «{}» field value '{}' did not match the «date» field part '{}' "
                                    "(required format is {})".format(result_dict["fld"], lookup[ix][0],
                                                                     date_parts[ix], part, lookup[ix][1])
                                )
                if ix == 9:
                    for ix, lookup_tuple in enumerate(lookup):
                        if date_parts[ix]:
                            try:
                                datetime.strptime(date_parts[ix], lookup_tuple[2])
                            except Exception:
                                DictValidator.add_entry(
                                    result_dict,
                                    "errors",
                                    "In «{}» the «{}» field value '{}' was invalid (required format is {})".format(
                                        result_dict["fld"], lookup_tuple[0], date_parts[ix], lookup_tuple[1])
                                )

            validation_dict = {
                "optional_keys": {"season": None,
                                  "publication_format": ["electronic", "printed", "print"]
                                  },
                "obj_validator_fn": _validate_date_dict
            }
            desirable_or_essential_keys = {
                "date": None,
                "year": None,
                "month": None,
                "day": None
            }
            if self.type == BEFORE_PUB:
                validation_dict["desirable_keys"] = desirable_or_essential_keys
            else:
                validation_dict["essential_keys"] = desirable_or_essential_keys

            # Validate publication date (must be provided as a list element)
            dv.validate_dict_list(result_dict, [date_dict], **validation_dict)

        def _validate_licences(result_dict, lic_list, key):
            """
            This ENCLOSURE uses `dv` (dict validator instance) from outer scope.

            if Publisher submits UPON publication,
                if there IS a default licence set
                    then URL Optional
                else
                    URL Mandatory
            else
                URL Desirable
            Licence NOT creative commons, then flag warning

            If > 1 licence, then all but one must have a Start date

            "license_ref" : [{
                "title" : "<name of licence>",
                "type" : "<type>", /* For example would be used to indicate <ali:free_to_read> or other e.g. cc-by */
                "url" : "<url>",
                "version" : "<version>",
                "start" : "<Date licence starts>",
                "best" : "<Boolean indicates if best licence>"
            }],
            :param result_dict: Dict - holds control information and validation results
            :param lic_list: List of licences to validate
            :param key: String - key of value being validated (or "~" if validating a `root` field)
            :return:
            """

            def _validate_url(result_dict, url, key):
                if url and not regex_check_creativecommons.match(url) and OPEN_LICENCE_SUBSTR not in url:
                    DictValidator.add_entry(
                        result_dict,
                        "issues",
                        f"In «{result_dict['fld']}» a non-creativecommons licence URL '{url}' appears - may be OK if intentional"
                    )

            validation_dict = {
                "optional_keys": {"title": None,
                                  "type": None,
                                  "version": None,
                                  "start": _validate_date
                                  },
                "star_dict": {"start": "*"}
            }

            # If publisher submits BEFORE publication  --> licence URL desirable
            if self.type == BEFORE_PUB:
                validation_dict["desirable_keys"] = {"url": _validate_url}
            # Else publisher submits UPON publication & a default licence is set --> licence URL optional
            elif self.pub_data.license.get("url"):
                validation_dict["optional_keys"]["url"] = _validate_url
            # Else publisher submits UPON publication & no default  --> licence URL essential
            else:
                validation_dict["essential_keys"] = {"url": _validate_url}

            # Validate list of licence dicts
            dv.validate_dict_list(result_dict, lic_list, **validation_dict)

            # Check that if more than 1 licence then all but one have a start date
            if result_dict["stars"] < result_dict["count"] - 1:
                DictValidator.add_entry(
                    result_dict,
                    "errors",
                    f"A licence «start» date is required for all but one of the «{result_dict['fld']}» elements"
                    f" ({result_dict['stars']} were " f"found in {result_dict['count']} licences)"
                )

        def _validate_page_info(result_dict, article_dict, key):
            """
            Check whether any of following desirable values are present: start_page, end_page, e_num, page_range.
            If page_range is present, then at least one of start_page & end_page will ALSO be present.

            :param result_dict: Dict - holds control information and validation results
            :param article_dict: article dict
            :param key: String - key of value being validated (or "~" if validating a `root` field)
            :return:
            """
            if article_dict.get("page_range"):
                for field in ("start_page", "end_page"):
                    if not article_dict.get(field):
                        DictValidator.add_entry(result_dict, "issues",
                                                f"«metadata.article.{field}» is missing (desirable field)")
            elif not article_dict.get("e_num"):
                # Add either as issue or error depending on whether articles are being sent before or upon publication
                # (page information should be known upon publication)
                DictValidator.add_entry(result_dict,
                                        "issues" if self.type == BEFORE_PUB else "errors",
                                        "«metadata.article» has missing page information - either «page_range» "
                                        "or «e_num» (electronic location number) should be provided"
                                        )

        ### Validation Definitions ###

        ## In the following 2 dicts, the Validator must be one of these 4 things:
        #   * None - No special validation, the validator just checks if field is Missing or Empty
        #   * ['List', 'of', 'allowed', 'values'] - As well as checking if field is Missing or Empty, it will be
        #       checked against this list of allowed values
        #   * Validation-function - As well as checking if field is Missing or Empty, if there is a value it will be
        #       passed to the validation function for bespoke validation
        #   * Validation-dict with at least one of the following keys: {
        #                                                              "essential_keys" : list or dict,
        #                                                              "optional_keys":  list or dict,
        #                                                              "star_dict": {"type": "reqd-value"},
        #                                                              "obj_validator_fn": validation_function
        #                                                              }


        # Common rules apply IRRESPECTIVE of the Route by which notifications arrive and the Agreement-type
        common_validation_rules = {
            "optional": {
                "metadata.contributor": _validate_contributors,
                "metadata.peer_reviewed": None,
            },
            "desirable": {
                # "field-dot-notation": Validator
                "metadata.journal.issue": None,
                "metadata.article.type": None,
                "metadata.article.abstract": None,
                "metadata.article.subject": None,
                "metadata.funding": {
                    "essential_keys": ["name"],
                    "desirable_keys": {"identifier": {"essential_keys": ["type", "id"]},
                                       "grant_numbers": None}
                },
                "metadata.ack": None,
            },
            "mandatory": {
                # "field-dot-notation": Validator
                "metadata.journal.title": None,
                "metadata.journal.publisher": None,
                "metadata.journal.identifier": {"essential_keys": ["type", "id"]},
                "metadata.article.title": None,
                "metadata.article.version": ["AM", "P", "VOR", "EVOR", "CVOR", "C/EVOR"],
                "metadata.article.identifier": _validate_article_identifier,
                "metadata.author": _validate_authors,
                "metadata.accepted_date": _validate_date,
                "metadata.license_ref": _validate_licences  # NB. Optionality is handled within _validate_licences
            }
        }
        # Variable rules depend on either the Route by which notifications are submitted or the Publisher Agreement-type
        variable_validation_rules = {
            ### necessity codes are: "o"=Optional, "d"=Desirable, "m"=Mandatory or None for no validation ###

            # necessity-code depends on Route by which notifications arrive: FTP or API
            "route": {
                # Each dict element has a Validation Tuple of 3 elements:
                #      "field-dot-notation": (FTP-route-necessity, API-route-necessity, Validator)
                # "field-dot-notation": Validator
                "event": (None, "o", ["submitted", "accepted", "published", "corrected", "revised"]),
                "metadata.publication_status": (None, "m", ["Published", "Accepted"]),
                "metadata.article.language": ("d", "m", None),
                },
            # necessity-code depends on Agreement-Type (when submitted): "u" (Upon-publication), "b" (Before-pub.n)
            "type": {
                # Each dict element has a Validation Tuple of 3 elements:
                #    "field-dot-notation": (Upon-necessity, Before-necessity, Validator)
                "metadata.journal.volume": ("m", "d", None),
                "metadata.article": ("m", "d", _validate_page_info),
                "metadata.publication_date": ("m", "d", _validate_pub_date),
                }
        }
        # Dict maps mode (route or type) to an index for accessing necessity values in the
        # `variable_validation_rules` tuple
        map_mode_to_ix = {
            # Route - FTP uses 1st tuple entry, API uses 2nd tuple entry
            "ftp": 0, "api": 1,
            # Type - Upon-publication uses 1st tuple entry, Before-publication uses 2nd tuple entry
            UPON_PUB: 0, BEFORE_PUB: 1
        }

        ### VALIDATION MAIN ###

        # Remove the "type" attribute (set to "U" when creating an UnroutedNotification), which isn't validated
        # or wanted in the compressed JSON which is saved
        try:
            del note_dict["type"]
        except KeyError:
            pass
        self.doi = self.get_doi_from_note_dict(note_dict)
        self.compressed_json = dict_to_json_compressed_base64(note_dict)

        dv = DictValidator()
        # Process common rules
        for necessity, fields_dict in common_validation_rules.items():
            # Loop for each field specified
            for field_dot_notation, validator in fields_dict.items():
                dv.root_validate(
                    field_dot_notation,
                    dictionary_get_dot_notation(note_dict, field_dot_notation),     # Value
                    validator,
                    necessity[:1]      # Get first character - Required indicator: one of 'o', 'd', 'm'
                )

        # Process variable rules
        for mode, fields_dict in variable_validation_rules.items():
            # get either self.route or self.type - should be one of the keys of dict map_mode_to_ix
            mode_value = self.__getattribute__(mode)
            required_ix = map_mode_to_ix.get(mode_value, 0)
            for field_dot_notation, validation_tuple in fields_dict.items():
                necessity = validation_tuple[required_ix]     # Required indicator: one of 'o', 'd', 'm'
                if necessity is not None:
                    dv.root_validate(
                        field_dot_notation,
                        dictionary_get_dot_notation(note_dict, field_dot_notation),     # Value
                        validation_tuple[2],  # Validator - either None, a List, a Dict or a Function
                        necessity
                    )

        # Create error, issue & info messages
        dv.generate_errors_issues_info_from_results_dict()
        # print("\n***** FULL RESULTS *****:\n", dv.validation_results, "\n")

        # Output messages to log - Returns tuple (error-count, issue-count, info-count)
        return dv.log_errors_issues_info_from_results_dict(self.log)
