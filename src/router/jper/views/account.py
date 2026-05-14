"""
Blueprint for providing account management of BOTH Organisation (AccOrg) and User (AccUser) Accounts.
(Account records are stored in separate DB tables: AccOrg -> `account`; AccUser -> `acc_user`).

**NOTE** that AccUser object may contain its parent AccOrg object (the exception is when an AccUser is retrieved on its
own, without its associated organisation record).

"""
import uuid
import requests
import re
from json import load, dumps
from operator import itemgetter
from urllib.parse import quote
from io import BytesIO
from os import listdir
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from flask import Blueprint, request, url_for, flash, redirect, current_app, jsonify, send_file, render_template, abort,\
    make_response, send_from_directory
from flask_login import login_user, logout_user
from octopus.lib.csv_files import create_in_memory_csv_file
from octopus.lib.data import json_str_from_json_compressed_base64, make_sortable_str, encode_tags_adjust_whitespace, truncate_string
from octopus.lib.dates import now_str, any_to_datetime, now_obj
from octopus.lib.mail import MailMsg, MailAccount
from router.shared.models.sword_out import SwordDepositRecord, FAILED
from router.shared.models.note import RoutedNotification
from router.shared.models.account import AccOrg, AccUser, AccNotesEmails, AccBulkEmail, AccRepoMatchParams,\
    AccRepoMatchParamsArchived, OFF, OKAY, FAILING
from router.shared.models.doi_register import dup_desc_dict, dup_desc_list, DUP_NONE, DUP_ULTRA_DIFF, DUP_ANY_DIFF, DUP_WITH_PDF
from router.shared.models.harvester import HarvesterWebserviceModel
from router.jper.models.publisher import PublisherDepositRecord, PubTestRecord
from router.jper.models.repository import MatchProvenance
from router.jper.models.identifier import Identifier
from router.jper.api import ParameterException
from router.jper.forms.account import AddOrgForm, RepoSettingsForm, RepoDuplicatesForm, PubSettingsForm,\
    PubReportsForm, PubTestingForm, OrgIdentifiersForm, MatchSettingsForm, OrgDataForm,\
    PasswordUserForm, UserDetailsForm, CompareMatchParamsForm
from router.jper.views.webapi import post_patch_matching_params
from router.jper.views.utility_funcs import get_page_details_from_request, calc_num_of_pages
from router.jper.security import admin_org_only__gui, org_user_or_admin_org__gui, own_user_acc_or_org_admin_or_admin_org__gui,\
    user_admin_or_admin_org__gui, admin_org_only_or_401__gui, org_user_or_admin_org_or_401__gui, json_abort

# scroll_num values: help ensure that Scrollers use unique connections (though uniqueness is conferred by scroll_name
# which is a composite of scroll_num, pull_name and other attributes).
# IMPORTANT check entire code base for other similar declarations before adding new ones (or changing these numbers) to
# avoid overlaps - do global search for "_SCROLL_NUM ="
NOTES_WITH_PROV_DOI_SCROLL_NUM = 20
NOTES_WITH_PROV_DATE_SCROLL_NUM = 21
NOTES_WITH_REPO_NAMES_SCROLL_NUM = 22
NOTES_WITH_PROV_NOTEID_SCROLL_NUM = 23

email_validator_regex = re.compile(r'^(?:[-_+a-z0-9]+\.?)+(?<!\.)@(?![.-])(?:\.?[-_+a-z0-9]+)+(?<![.-])$', re.IGNORECASE)
# email_separators = re.compile(r'[;, \n\r]+')     # Email string will be split on these characters into a list
email_separators = re.compile(r'[;, ]+')     # Email string will be split on these characters into a list
doi_starts_with_regex = re.compile(r'^(?:\*|10\.)')  # If string starts with '*' or '10.'
# Match a string like: "doi:...", "http://dx.doi.org/...", "https://doi.org/..."
match_doi_prefix = re.compile(r"^(?:(?:https?://)?(?:dx\.)?doi\.org/|doi:)(.+)")

blueprint = Blueprint('account', __name__)


def retained_months(table_name="notification"):
    # Return number of months for particular doc-type from the scheduled-deletion dict which has structure:
    # { Doc-type: (Index, Months-to-keep), ... }
    return current_app.config.get("SCHEDULED_DELETION_DICT", {}).get(table_name, ("", 3))[1]


def _relative_to_today(days=0, months=0, years=0):
    return datetime.today() + relativedelta(days=days, months=months, years=years)


def _wtforms_validation_error_string(wtform, prefix_msg='', msg_join=' '):
    """
    Retrieve  validation errors and convert into an error string which is returned

    :param wtform: The form that has been validated
    :param prefix_msg: First part of message to return
    :param msg_join: Joining string that will be used to concatenate separate error messages
    :return: Error string
    """
    # Get validation errors
    errors = []
    # wtform.errors is a dict like: { 'field-name': field-errors-list } so we combine all field errors-lists into one
    for err_list in wtform.errors.values():
        errors += err_list

    err_msg = prefix_msg + msg_join.join(errors)
    # Append a terminating fullstop if needed
    # if not err_msg.endswith('.'):
    #     err_msg += '.'
    return err_msg


def _get_files_from_dir(directory, ends_with, sort_desc=True):
    try:
        reports = [fl for fl in listdir(directory) if fl.endswith(ends_with)]
        reports.sort(reverse=sort_desc)
    except:
        reports = []
    return reports


def _abort(err_code, err_msg="", display_error=True):
    code_desc = {
        400: "Bad Request",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Not Found",
        405: "Not Allowed"
    }
    if display_error:
        abort(make_response(render_template('error.html', title=code_desc.get(err_code, "Error"), error_msg=err_msg),
                            err_code))
    else:
        abort(err_code)

def _validate_json_dict(json_dict, reqd_keys):
    errors = []
    for k in reqd_keys:
        if not json_dict.get(k):
            errors.append(k)
    if errors:
        raise Exception(" and ".join(errors) + (" field is" if len(errors) == 1 else " fields are") + " required")

    if len(json_dict.get("body", "")) > 8000:
        raise Exception("Message size exceeds 8000 characters")
    return json_dict


def _validate_emails(email_addrs_string):
    """
    Validate a text field that can hold Multiple email addresses, separated by comma, semicolon or space and
    convert to a list of emails.

    :param email_addrs_string: String of emails
    :return: list of emails OR Exception raised
    """
    # Split string on comma, semicolon or space
    email_addr_list = []
    bad_emails = []
    for addr in email_separators.split(email_addrs_string.strip(" ,;\n\r\t")):
        if addr:
            if email_validator_regex.match(addr):
                email_addr_list.append(addr)
            else:
                bad_emails.append(f"'{addr}'")

    if bad_emails:
        raise Exception(
            f"Invalid email address{'' if len(bad_emails) == 1 else 'es'} entered: {', '.join(bad_emails)}")

    return email_addr_list


# Organisation Account listing (list all accounts)
@blueprint.route('/')
@admin_org_only__gui
def index(curr_user=None, cu_org_acc=None):
    """
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    """
    users = AccOrg.get_all_undeleted_accounts_of_type(order_by="role ASC")
    return render_template(
        'account/org_acs.html',
        curr_user_acc=curr_user,
        org_acs=users,
        title="Manage all organisations",
        days_since_deposit_fn=PublisherDepositRecord.days_since_last_deposit,
        sort_col=1,  # initially sort on column 1
        make_sortable_str=make_sortable_str
    )


# List publisher accounts
@blueprint.route('/publishers', methods=['GET'])
@blueprint.route('/publishers/<auto_test>', methods=['GET'])
@admin_org_only__gui
def manage_publishers(auto_test=None, curr_user=None, cu_org_acc=None):
    """

    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    :param auto_test: Indicates required auto-testing status
    """
                        # URL-segment: (Title-modifier-text, kwargs-dict-for-get_publishers )
    map_arg_to_kwarg = {"autotest": ("autotest ", {"auto_test": "active"}),
                        "no_autotest": ("non-autotest ", {"auto_test": "inactive"})}
    title_modifier, kwargs = map_arg_to_kwarg.get(auto_test, ("", {}))
    users = AccOrg.get_publishers(**kwargs)
    return render_template(
        'account/org_acs.html',
        curr_user_acc=curr_user,
        org_acs=users,
        title=f"Manage {title_modifier}publishers",
        days_since_deposit_fn=PublisherDepositRecord.days_since_last_deposit,
        sort_col=2,  # initially sort on column 2
        make_sortable_str=make_sortable_str
    )


# List repository accounts
# IMPORTANT: livetest_status is specified as a `path` as a work-around to enable a variable number of '/' 
# separated parameters to be passed: live|test or on|off|problem or live|test/on|off|problem
@blueprint.route('/repositories', methods=['GET'])
@blueprint.route('/repositories/<path:livetest_status>', methods=['GET'])
@admin_org_only__gui
def manage_repositories(livetest_status="", curr_user=None, cu_org_acc=None):
    """
    Lists repository accounts, possibly filtered to show only those that are live or Test; and/or On, Off or with Problems

    :param livetest_status: String, one of:
        ["live"|"test"|"on"|"off"|"problem"|"live/on"|"live/off"|"live/problem"|"test/on"|"test/off"|"test/problem"]
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    :return: Renders new GUI screen
    """
    title_insert = ""
    livetest = "LT"
    status = ""
    _livetest, _, _status = livetest_status.lower().partition("/")
    if _livetest:
        if _livetest in ("test", "live"):
            title_insert = _livetest + " "
            livetest = _livetest[0].upper()   # First character, UPPER case
            status = _status
        else:
            status = _livetest

    if status not in ("", "on", "off", "problem"):
        _abort(404, "Invalid URL. Expected repositories/(test|live/)on|off|problem.")

    if status:
        title_insert += status + " "
    return render_template(
        'account/org_acs.html',
        curr_user_acc=curr_user,
        org_acs=AccOrg.get_repositories(livetest, status),
        title=f"Manage {title_insert}repositories",
        days_since_deposit_fn=None,  # This only needed if displaying publishers (not repositories)
        sort_col=2,  # initially sort on column 2
        make_sortable_str=make_sortable_str
    )


# List problem accounts.  Possible parameters: past_days/all
# IMPORTANT: past_days_all is specified as a `path` as a work-around to enable a variable number of '/' separated
# parameters to be passed
@blueprint.route('/errors/<pub_or_repo>', methods=['GET'])
@blueprint.route('/errors/<pub_or_repo>/<path:past_days_all>', methods=['GET'])
@admin_org_only__gui
def recent_errors(pub_or_repo=None, past_days_all="", curr_user=None, cu_org_acc=None):
    """
    Lists problem accounts, together with their recent errors from past X days (default 7) together with a panel for
    each account showing history of notes/emails sent & a form for entering/sending a new note/email, including
    attaching error messages to the email.

    :param pub_or_repo: String, one of ["publisher"|"repository"]
    :param past_days_all: String, OPTIONAL - expected to be one of: xxx/all or all/xxx or xxx or all -
                    - retrieve data for past x number of days
                    - retrieve all repositories, not just failing
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    :return: Renders new GUI screen
    """

    def _check_last_account_metdata_error_count_maybe_zeroise():
        """
        Function is called whenever all errors for a particular account have been processed.

        It checks whether the most recent metadata error (if one exists) has occurred fewer than 3 times - if so
        it zeroises the repo-metadata-error-note-id value (this prevents display of the Skip notification button).
        In other words, only if a metadata error has occurred at least 3 times is it possible to skip past it.
        """
        # If, for last account processed, the metadata_err_count is less than 3
        if first_metadata_err_note_id and metadata_err_count < 3:
            ac_details[-1][8] = 0  # Set the LAST acc details Repo-metadata-error-note-id to zero

    if pub_or_repo not in ("publisher", "repository"):
        _abort(404, "Invalid URL segments - options: /errors/publisher|repository.")

    past_all_list = past_days_all.split("/")
    len_past_all = len(past_all_list)
    past_days = "7"  # Default
    is_all = None
    if len_past_all == 1: # either got xxx or all
        past_days = past_all_list[0]
        if not past_days.isdigit():     # Assume "all" was passed
            is_all = past_days
            past_days = "7"
    elif len_past_all == 2:   # Should have got xxx/all or all/xxx
        past_days = past_all_list[0]
        is_all = past_all_list[1]
        # if we DIDN'T get xxx/all, then try for all/xxx
        if is_all != "all":
            is_all = past_days
            past_days = past_all_list[1]

    if len_past_all > 2 or not past_days.isdigit() or (is_all and is_all != "all"):
        _abort(404, "Invalid URL. Expected …/<num> or …/all or …/<num>/all or …/all/<num>.")

    if is_all == "all":
        min_status = OFF
    else:
        min_status = OKAY if pub_or_repo == "repository" else OFF

    ac_details = []     # List of problem accounts (stores tuple of info for each account)
    err_details_dict = {}   # Dict, keyed by account-ID, storing lists of error record tuples
    last_acc_id = None
    # Within the loop, the logic determines whether at least 3 metadata errors for the same notification have occurred.
    #  If so, then the last field in `acc_details_list` (which stores the Repo-metadata-error-note-id) is left as-is;
    #  If 3 or fewer metadata errors have occurred, then that field is set to zero.
    # Note that `Repo-metadata-error-note-id` will be zero for Publishers or for Repo content-errors.
    first_metadata_err_note_id = None
    metadata_err_count = 0
    # Scroller returns RAW data - the Tech-contact-email list is returned as a string of elements separated by '|'
    # Record tuples returned:
    #   (AccID, UUID, API-key, Org-name, Live-or-test, Contact-email, Tech-contact-emails ('|' separated), Acc-status, Repo-metadata-error-note-id, Err-Date, Err-Msg (formatted), Err-ID, Err-emailed-bool)
    # ORDERED BY Org-name, Error-Date
    with AccOrg.get_errors_for_accounts_scroller(pub_or_repo, past_days, min_status) as scroller:
        for rec_tuple in scroller:
            # The `rec_tuple` is considered to have 2 parts:
            #   * Account part - slice [0:9], i.e. index 0 to 8 (inclusive)
            #   * Error part - slice [9:], i.e. index 9 to end (inclusive)
            # Last value in acc_part will be Non-zero only for Repo accounts, if a metadata error
            metadata_err_note_id = rec_tuple[8]
            # If a new account
            if rec_tuple[0] != last_acc_id:
                _check_last_account_metdata_error_count_maybe_zeroise()

                last_acc_id = rec_tuple[0]
                acc_details_list = list(rec_tuple[0:9])
                # If contact email is None, change to ""
                if acc_details_list[5] is None:
                    acc_details_list[5] = ""
                # Change tech_contact_emails '|' separated (list) string to '; ' separated string
                tech_emails = acc_details_list[6]
                acc_details_list[6] = tech_emails.replace("|", "; ") if tech_emails else ""
                # Change status value to description
                acc_details_list[7] = AccOrg.translate_status(acc_details_list[7])
                ac_details.append(acc_details_list)   # store account details tuple

                err_details_dict[last_acc_id] = []  # initialise error details dict entry for the account

                first_metadata_err_note_id = metadata_err_note_id
                metadata_err_count = 0

            # Count number of occurrences of the first metadata error note-ID
            if first_metadata_err_note_id and first_metadata_err_note_id == metadata_err_note_id:
                metadata_err_count += 1

            err_details_dict[last_acc_id].append(rec_tuple[9:])  # save error tuple in error-details dict

        # For the last account processed...
        _check_last_account_metdata_error_count_maybe_zeroise()

    return render_template(
        'account/recent_errors.html',
        curr_user_acc=curr_user,
        ac_details=ac_details,
        err_details_dict=err_details_dict,
        title=f"Recent {pub_or_repo} errors",
        past_days=past_days,
        content_href=current_app.config.get("API_URL") + "/{}/content?api_key=",
        accuser__pull_user_email_details_by_org_id_n_role=AccUser.pull_user_email_details_by_org_id_n_role,
        pub_or_repo_ind=pub_or_repo[:1].upper(),     # 'R' or 'P'
        cc_emails="; ".join(current_app.config.get("CONTACT_CC", []))
    )


def _get_org_acc_by_uuid(org_uuid, for_update=False, display_error=True):
    """
    Function to get Organisation Account from database using Org UUID.
    """
    org_acc = AccOrg.pull(org_uuid, pull_name="uuid", for_update=for_update)
    if org_acc is None:
        _abort(404, "Organisation account not found.", display_error=display_error)

    return org_acc


def _get_user_n_org_acc_by_uuid(user_uuid, display_error=True):
    """
    Function to get User Account (& it's parent Org Ac) from database using User UUID.
    NOTE that a DELETED user account can be returned.
    """
    user_acc = AccUser.pull_user_n_org_ac(user_uuid, "user_uuid")
    if user_acc is None:
        _abort(404, "User account not found.", display_error=display_error)

    return user_acc


def _get_user_acc_by_uuid(user_uuid, for_update=False, display_error=True):
    """
    Function to get User Account ONLY (Not it's parent Org Ac) from database using User UUID.
    """
    user_acc = AccUser.pull(user_uuid, pull_name="uuid", for_update=for_update)
    if user_acc is None:
        _abort(404, "User account not found.", display_error=display_error)

    return user_acc


def _get_jisc_core_id_dict(jisc_id=None, core_id=None):
    """
    Retrieve from the "Identifiers database" the Names associated with particular IDs and return
    a structure like:
        {'jisc_id': repository_data.jisc_id or '',
        'jisc_id_name': '',
        'core_id': repository_data.core_id or '',
        'core_id_name': ''
        }

    :param jisc_id: string JISC ID value may be
    :param core_id: CORE ID value (string)
    :return: dict
    """
    jisc_id_name = ""
    core_id_name = ""
    if jisc_id:
        id_obj = Identifier.pull("JISC", jisc_id)
        if id_obj:
            jisc_id_name = id_obj.name
    if core_id:
        id_obj = Identifier.pull("CORE", core_id)
        if id_obj:
            core_id_name = id_obj.name

    return {'jisc_id': jisc_id, 'jisc_id_name': jisc_id_name, 'core_id': core_id, 'core_id_name': core_id_name}


def _get_publisher_notification_sources_list():
    """
    Get publisher notification sources, sorted by name/description alphabetical order (excluding any deleted records).
    The returned list includes both true Publisher accounts and ALSO Harvester webservice accounts that are to be shown
    as Publishers

    :return: list of publisher-source dicts with values: {prefixed-id (string), name (string), active (boolean), live (boolean)}
    """
    pub_sources = [
        # Id is prefixed with "p" to indicate publisher-account
        {'id': f"p{pub.id}", 'name': pub.org_name, 'active': pub.status > 0, 'live': pub.live_date is not None}
        for pub in AccOrg.get_publishers()
    ] + [
        # Id is prefixed with "h" to indicate harvester-account
        {'id': f"h{pub['id']}", 'name': pub['name'], 'active': pub['active'], 'live': pub['live_date'] is not None}
        for pub in HarvesterWebserviceModel.get_harvester_dicts(pseudo_pub=True, reqd_fields=['id', 'name', 'active', 'live_date'])
    ]

    # Sort "publishers" by name (descending)
    return sorted(pub_sources, key=itemgetter('name'))


def _get_harvester_notification_sources_list():
    """
    Get harvester notification sources, sorted in name/description alphabetical order - EXCLUDING those that
    are to be shown as publishers

    :return: list of harvester-source dicts with values: {id (string), name (string), active (boolean), live (boolean)}
    """
    # Return list of harvester services: service-name, booleans: live (visible), active
    return [
        {'id': f"h{harv['id']}", 'name': harv['name'], 'active': harv['active'], 'live': harv['live_date'] is not None}
        for harv in HarvesterWebserviceModel.get_harvester_dicts(pseudo_pub=False, reqd_fields=['id', 'name', 'active', 'live_date'])
    ]


def _pub_test_disable_fields(pub_data, is_admin):
    """
    Return list of publisher testing fields to set as disabled
    :param pub_data: publisher data object
    :param is_admin: Boolean - True: Admin account; False: non-Admin account
    :return: List of field names TO DISABLE
    """
    fields_to_disable = ["in_test", "test_start", "test_end", "last_error", "last_ok", "num_err_tests",
                         "num_ok_tests", "num_ok_since_last_err"]  # Date strings can never be modified
    if is_admin:
        if pub_data.test_start:
            # Once a start date is set, cannot change the start_checkbox
            fields_to_disable += ["start_checkbox"]
            if pub_data.test_end:
                # Once testing has ended cannot pass test notifications through for processing
                fields_to_disable += ["route_note_checkbox"]
        else:
            # If testing not started, cannot tick end_checkbox or route_note_checkbox
            fields_to_disable += ["end_checkbox", "route_note_checkbox"]
    else:
        fields_to_disable += ["test_type", "start_checkbox", "end_checkbox", "route_note_checkbox"]
    return fields_to_disable


def _org_data(org_acc):
    return {
        "organisation_name": org_acc.org_name,
        "note": org_acc.note,
        "contact_email": org_acc.contact_email,
        "tech_contact_emails": org_acc.tech_contact_emails_string(),
    }


def _disp_org_acc(org_acc, curr_user_acc, curr_user_org_acc, **returned_values):
    """
    Display Org Account web page
    :param org_acc: Organisation Account object
    :param curr_user_acc: Currently logged in User Account object
    :param curr_user_org_acc: Currently logged in User's Organisation account
    :param returned_values: Possible data structures if redisplay after validation errors
    :return: render_template
    """
    read_only_user = curr_user_acc.is_read_only
    live_date_str = org_acc.live_date
    if live_date_str:
        live_date_str = datetime.strptime(live_date_str, '%Y-%m-%dT%H:%M:%SZ').strftime('%Y-%m-%d')

    # Init structures that may be empty depending on Organisation Account Role
    form_repo_ids = None
    form_repo_match = None
    form_repo_settings = None
    form_repo_duplicates = None
    form_pub_settings = None
    form_pub_reports = None
    form_pub_testing = None
    repo_data = None
    sources = None
    packaging_formats = None

    org_data_form = returned_values.get("org_data_form") or OrgDataForm(data=_org_data(org_acc),
                                                                        disable_fields=read_only_user)
    _config = current_app.config
    # Set "Repository only" data required by forms
    if org_acc.is_repository:
        repo_data = org_acc.repository_data

        packaging_formats = _config["REPOSITORY_PACKAGING_OPTIONS"]
        if "form_repo_settings" in returned_values:
            form_repo_settings = returned_values["form_repo_settings"]
        else:
            repo_form_data = {
                'repository_name': repo_data.repository_name,
                'repository_url': repo_data.repository_url,
                'repository_software': repo_data.repository_software,
                'sword_username': repo_data.sword_username,
                'sword_password': repo_data.sword_password,
                'sword_collection': repo_data.sword_collection
            }

            # Check if it exists, if it does add it to the form data - otherwise the form will take the form default
            target_queue = repo_data.repository_queue
            if target_queue:
                repo_form_data["target_queue"] = target_queue

            xml_format = repo_data.repository_xml_format
            if xml_format:
                repo_form_data["xml_format"] = xml_format

            packaging = repo_data.packaging
            if packaging:
                repo_form_data["packaging"] = packaging
            # Repository settings are disabled for Read-only Users or where
            # user is NOT a YOUR-ORG admin and Account is NOT live (i.e. is a Test account)
            form_repo_settings = RepoSettingsForm(data=repo_form_data,
                                                  disable_fields=read_only_user or not curr_user_org_acc.is_super and org_acc.live_date is None)

            # If we didn't have an xml_format, set it from the form default so we can use it to create the choices
            # for the packaging formats.
            if not xml_format:
                xml_format = form_repo_settings.xml_format.default

            # set up the packaging choices for this repository
            form_repo_settings.packaging.choices = packaging_formats.get(xml_format, [])

        form_repo_match = MatchSettingsForm(data={"pub_years": repo_data.max_pub_age}, disable_fields=read_only_user)

        form_repo_duplicates = returned_values.get("form_repo_duplicates") or RepoDuplicatesForm(
            data={'dups_level_pub': repo_data.dups_level_pub,
                  'dups_level_harv': repo_data.dups_level_harv,
                  'dups_emails': repo_data.dups_emails_as_str(),
                  'dups_meta_format': repo_data.dups_meta_format
                 },
            disable_fields=read_only_user
        )

        # If we're super, we need to retrieve the descriptions associated with the account's identifiers (if set)
        if curr_user_org_acc.is_super:
            form_repo_ids = OrgIdentifiersForm(data=_get_jisc_core_id_dict(repo_data.jisc_id, repo_data.core_id),
                                               disable_fields=read_only_user)
        sources = {
            'pub_sources': _get_publisher_notification_sources_list(),
            'harv_sources': _get_harvester_notification_sources_list(),
            'excluded_provider_ids': ','.join(repo_data.excluded_provider_ids)
        }

    # Set "Publisher only" data required by forms
    elif org_acc.is_publisher:
        pub_data = org_acc.publisher_data
        license = pub_data.license
        form_pub_settings = returned_values.get("form_pub_settings") or PubSettingsForm(
            data={
            'embargo_duration': pub_data.embargo,
            'license_title': license.get("title"),
            'license_type': license.get("type"),
            'license_url': license.get("url"),
            'license_version': license.get("version"),
            'peer_reviewed': pub_data.peer_reviewed
            },
            disable_fields=read_only_user)

        ## Publisher report settings ##
        form_pub_reports = returned_values.get("form_pub_reports") or PubReportsForm(
            data=pub_data.get_report_data_for_form(),
            disable_fields=read_only_user)

        ## Publisher testing settings ##
        form_pub_testing = returned_values.get("form_pub_testing") or PubTestingForm(
            data=pub_data.get_test_data_dict_for_form(),
            disable_fields=read_only_user or _pub_test_disable_fields(pub_data, curr_user_org_acc.is_super))

    return render_template('account/org_ac.html',
                           title=f"Account Details for {org_acc.org_name}",
                           curr_user_acc=curr_user_acc,
                           org_acc=org_acc,
                           repoconfig=repo_data,
                           packaging_formats=packaging_formats,
                           basic_form=org_data_form,
                           form_ids=form_repo_ids,
                           form_match=form_repo_match,
                           form_repo_settings=form_repo_settings,
                           form_repo_duplicates=form_repo_duplicates,
                           duplicate_desc_dict=dup_desc_dict,
                           duplicate_desc_list=dup_desc_list,
                           days_since_deposit_fn=PublisherDepositRecord.days_since_last_deposit,
                           sources=sources,
                           form_pub=form_pub_settings,
                           form_pub_reports=form_pub_reports,
                           form_pub_test=form_pub_testing,
                           live_date=live_date_str,
                           env=_config["OPERATING_ENV"],
                           docu_api_url=_config.get("DOCU_API_URL", ""),
                           sftp_address=_config.get("SFTP_ADDRESS", ""),
                           sword_address=_config.get("SWORD_ADDRESS", ""),
                           cc_emails="; ".join(_config.get("CONTACT_CC", []))
                           )

def _deposit_record_history_to_template_variables(cu_org_acc,
                                                  role,
                                                  uuid,
                                                  report_func,
                                                  link_template=None,
                                                  from_date_default_days_offset=None,
                                                  content_href=None,
                                                  page_required=True,
                                                  display_error=True):
    """
    Given some deposit records, change them to template variables for use with render_template.

    The kwargs dict will also be given to the CSV calculator - although not applied to render template.

    :param cu_org_acc: Object - Current user's Org account
    :param role: string: "publisher"|"repository".
    :param uuid: The publisher or repository UUID.
    :param report_func: Function used to retrieve aggregate data
    :param link_template: URL formatting string (e.g. "/account/{}/deposit_history")
    :param from_date_default_days_offset: Integer or None - number days from today to set default-from-date to
    :param content_href: None or string template for constructing a content download link
    :param page_required: Boolean - True: Expect a page to be specified (default will be applied), False: Page optional
    :param display_error: Boolean - True: If error then display webpage with error; False: Simple abort (e.g. if returning JSON)
    :return: Dict of aggregate data if everything is correct or Aborts with error code
    """
    org_acc = _get_org_acc_by_uuid(uuid) if cu_org_acc.is_super else cu_org_acc
    # If the account isn't the required role then abort with a 400.
    if not org_acc.has_role(role):
        _abort(400, "Account has wrong role", display_error=display_error)

    from_date = request.args.get("from_date")
    to_date = request.args.get("to_date")
    # Returned value of `page` will either be an integer > 0, or None.
    page, page_size = get_page_details_from_request(request.args, 1 if page_required else None)

    # No to-date is provided, and defaults are required
    if not to_date:
        today = datetime.today()
        to_date = today.strftime("%Y-%m-%d")
        if not from_date and from_date_default_days_offset is not None:
            from_date = (today - relativedelta(days=from_date_default_days_offset)).strftime("%Y-%m-%d")
    if not from_date:
        from_date = "2000-01-01"    # Beginning of time (from Router perspective)

    # Defaults in case an error happens.
    error = None
    data_iterable = col_headings = None
    try:
        total_count, data_iterable, col_headings = report_func(
            org_acc.id, from_date=from_date, to_date=to_date, page=page, page_size=page_size)
    except ValueError as e:
        error, obj = e.args
        error = f"{error}: {obj}"
        flash(error, 'error')
    except Exception as e:
        error = str(e)
        current_app.logger.critical(
            f"Unexpected query failure while executing function '{report_func.__name__}': {repr(e)}",
            exc_info=True)
        flash("An unexpected error occurred.", 'error')

    ret_dict = {
        "uuid": org_acc.uuid,
        # Use a substitute if Org Name is blank
        "org_name": org_acc.org_name or "Account_" + org_acc.uuid,
        "data_iterable": data_iterable,
        "col_headings": col_headings
    }
    # link_template will be provided where data is for GUI display
    if link_template:
        if not error:
            num_of_pages = calc_num_of_pages(page_size, total_count) if total_count is not None else None
            link_with_id = link_template.format(uuid)
            from_to_params = f"?from_date={from_date}&to_date={to_date}"
            link = link_with_id + from_to_params
            csv_link = link_with_id + "/csv" + from_to_params
        else:
            # If we have an error, set the page to 1 to make sure we don't have any odd pagination boxes.
            page = 1
            num_of_pages = 0
            link = ""
            csv_link = ""
        # Add additional values to returned dictionary
        ret_dict.update({
            "num_of_pages": num_of_pages,
            "page": page,
            "link": link,
            "csv_link": csv_link,
            "from_date": from_date,
            "to_date": to_date,
            "content_href": content_href + org_acc.api_key if content_href else ""
        })
    return ret_dict


def _create_new_user_acc(org_id, user_data):
    """
    Create & insert a new AccUser record.
    @param org_id: Int - ID of parent organisation account
    @param user_data: Dict of user data values
    @return: Tuple: (new AccUser-object, password-reset-URL)
    """
    user_acc = AccUser()
    user_acc.username = user_data["username"]
    user_acc.user_email = user_data["user_email"]
    user_acc.surname = user_data["surname"]
    user_acc.forename = user_data["forename"]
    user_acc.org_role = user_data["org_role"]
    user_acc.role_code = user_data["role_code"]
    user_acc.direct_login = user_data["direct_login"]
    user_acc.note = user_data["user_note"]
    user_acc.org_id = org_id  # Parent Organisation Account
    # Use supplied password or generate a random one
    user_acc.set_password(user_data["password"] or user_acc.create_uuid())
    password_reset_token = user_acc.create_reset_token()
    user_acc.failed_login_count = 0
    user_acc.insert()  # This generates the UUID

    # Need to pass _scheme=... because URL was defaulting to "http" for some reason (at least in UAT)
    return user_acc, url_for(
        "account.reset_password", user_uuid=user_acc.uuid, token_val=password_reset_token["value"],
        _external=True, _scheme=current_app.config["PREFERRED_URL_SCHEME"])


def _delete_user_acc(user_acc, str_timestamp, commit=True):
    """
    Mark user account as deleted - return info String.

    # The user account record will remain with a 'deleted' date set (it is important that the account record remains).

    @param user_acc: Obj - User account object
    @param str_timestamp: String - Timestamp (like '2024-01-24T13:40:26Z')
    @param commit: Boolean - whether to commit record or not
    @return: String - Info about record deleted
    """
    user_acc.deleted_date = str_timestamp
    # Change otherwise it cannot be re-used
    user_acc.username = f"DELETED_{str_timestamp}_{user_acc.username}"
    user_acc.update(commit=commit)
    return f"DELETED {user_acc.role_desc} User Account {user_acc.uuid} ({user_acc.forename} {user_acc.surname})"


# Add new Organisation account (One of: Admin|Publisher|Repository)
@blueprint.route('/register', methods=['GET', 'POST'])
@admin_org_only__gui
def register(curr_user=None, cu_org_acc=None):
    """
    This creates an Organisation Account and a first User Account.
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    :return:
    """
    add_org_form = AddOrgForm(request.form)
    add_org_form.set_role_code_choices("AS")
    if request.method == 'POST':
        if add_org_form.validate():
            try:
                # The Add Organisation form captures Organisation details and the first User's details
                org_n_user_data = add_org_form.data
                org_acc = AccOrg()
                org_acc.org_name = org_n_user_data['organisation_name']
                org_acc.contact_email = org_n_user_data['contact_email']
                org_acc.api_key = str(uuid.uuid4())
                org_acc.tech_contact_emails = add_org_form.tech_contact_emails.email_list  # This list set by validation code
                org_acc.note = org_n_user_data['note']
                role = org_n_user_data['role']
                org_acc.role = role
                
                if role == "repository":
                    org_acc.status = OKAY
                    repo_data = org_acc.repository_data

                    repo_data.dups_level_pub = DUP_WITH_PDF     # Duplicates with additional metadata or with a full-text PDF
                    repo_data.dups_level_harv = DUP_NONE        # No duplicates
                    ## Below are perhaps better default values than those above##
                    # repo_data.dups_level_pub = DUP_ANY_DIFF    # Dups with discernible difference
                    # repo_data.dups_level_harv = DUP_ULTRA_DIFF    # Dups with main difference

                    # Set default Excluded notification sources
                    harvester_template = AccOrg.provider_id_template[True]     # Template for excluded provider list harvester Ids
                    excluded_harvesters = [ harvester_template.format(_id) for _id in
                                            HarvesterWebserviceModel.get_auto_enable_harvester_ids(auto_enabled=False)]
                    repo_data.excluded_provider_ids = excluded_harvesters
                # default publisher's roles to "off" on creation
                elif role == "publisher":
                    org_acc.status = OFF
                    pub_data = org_acc.publisher_data
                    pub_data.init_testing()
                else:   # Must be admin Org account
                    org_acc.status = OKAY
                    org_n_user_data["role_code"] = "J"     # Initial user-role always a Jisc-Admin

                # Need to save before creating FTP account, as creates 'id' value & don't want to create FTP account if
                # Org Account record creation raises exception. It also generates UUID
                org_acc.insert()

                # Make sure UNIX FTP accounts are enabled before creating the FTP user
                if role == 'publisher' and current_app.config.get("UNIX_FTP_ACCOUNT_ENABLE", True):
                    org_acc.create_ftp_account()

                ## Create first user account (usually an Admin account)
                user_acc, pwd_reset_url = _create_new_user_acc(org_acc.id, org_n_user_data)
                admin_ac_reset_link = f'<a href="{pwd_reset_url}">Password reset link for new user</a>'
                admin_ac_url = url_for('.user_account', org_uuid=org_acc.uuid, user_uuid=user_acc.uuid)

                message = f"Accounts created for Organisation: <strong>{org_acc.org_name}</strong>; Organisation admin user: <strong><a href=\"{admin_ac_url}\">{user_acc.forename} {user_acc.surname}</a></strong>. {admin_ac_reset_link} for emailing to Organisation administrator."
                flash(message, 'success+html')
                return redirect(url_for('.disp_org_acc', org_uuid=org_acc.uuid))

            except Exception as e:
                # Display e.message if it exists, otherwise general error
                flash(getattr(e, 'message', 'There was a problem with your submission'), "error")
        else:
            flash(_wtforms_validation_error_string(add_org_form, "Data entry error: ", "; "), "error")

    return render_template(
        'account/register.html',
        curr_user_acc=curr_user,
        title='Register a New User',
        add_org_form=add_org_form
    )


# @blueprint.route('/<account_id>/api_key', methods=['POST'])
# @org_user_or_admin_org__gui()
# def apikey(account_id):
#
#     acc = _get_org_acc_by_uuid(account_id)
#     acc.data['api_key'] = str(uuid.uuid4())
#     acc.save(blocking=True)
#     flash('Your API key has been updated.', "success")
#     return redirect(url_for('.disp_org_acc', org_uuid=account_id))


# Display Organisation account page, by specified Org UUID
@blueprint.route('/<org_uuid>', methods=['GET'])
@org_user_or_admin_org__gui()
def disp_org_acc(org_uuid, curr_user=None, cu_org_acc=None):
    """
    :param org_uuid: UUID of organisation to be displayed
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    """
    # If current org-user is Admin, then we want to retrieve Org Account that the Admin user selected (will abort
    # with 404 if not found); otherwise we just use the user's parent Org Account
    org_acc = _get_org_acc_by_uuid(org_uuid) if cu_org_acc.is_super and cu_org_acc.uuid != org_uuid else cu_org_acc
    return _disp_org_acc(org_acc, curr_user, cu_org_acc)


# Make account Live
@blueprint.route('/<org_uuid>/golive', methods=['POST'])
@admin_org_only__gui
def golive(org_uuid, curr_user=None, cu_org_acc=None):
    """
    :param org_uuid: UUID of organisation to be displayed
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    """
    org_acc = _get_org_acc_by_uuid(org_uuid, for_update=True)
    org_acc.live_date = now_str()
    if org_acc.is_publisher:
        pub_data = org_acc.publisher_data
        if pub_data.in_test:
            pub_data.end_testing()
            current_app.logger.info(f"Auto-testing ENDED for publisher account '{org_acc.org_name}' ({org_acc.id}).")

    org_acc.update()
    current_app.logger.info(f"Made {org_acc.role} account '{org_acc.org_name}' ({org_acc.id}) LIVE.")
    flash('Your account status has been changed to LIVE.', "success")
    return redirect(url_for('.disp_org_acc', org_uuid=org_uuid))


# Update Org account settings (Org name, contact email etc.)
@blueprint.route('/<org_uuid>/update_settings', methods=['POST'])
@org_user_or_admin_org__gui()
def update_settings(org_uuid, curr_user=None, cu_org_acc=None):
    """
    :param org_uuid: UUID of organisation to be displayed
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    """
    org_acc = _get_org_acc_by_uuid(org_uuid, for_update=True)
    org_data_form = OrgDataForm(request.form, data=_org_data(org_acc), acc_id=org_acc.id, disable_fields=curr_user.is_read_only)
    if org_data_form.validate():
        org_acc.org_name = org_data_form.organisation_name.data
        org_acc.note = org_data_form.note.data
        org_acc.contact_email = org_data_form.contact_email.data
        org_acc.tech_contact_emails = org_data_form.tech_contact_emails.email_list    # This list is populated by email validation code
        org_acc.update()
        flash("Account settings updated", "success")
        return redirect(url_for('.disp_org_acc', org_uuid=org_uuid))
    else:
        org_acc.rollback()
        flash(_wtforms_validation_error_string(org_data_form, "Settings not updated: "), "error")
        return _disp_org_acc(org_acc, curr_user, cu_org_acc, org_data_form=org_data_form)


# Handle ajax requests related to Accounts - use by Jisc admin only
@blueprint.route('/admin_ajax/<org_id>', methods=['POST'])
@admin_org_only_or_401__gui
def admin_ajax(org_id):
    """
    Requests for the following functions:
    * Toggle repository or publisher account status Off <-> On (Succeeding)
    * Toggle repository status
    * Skip blocking notifications (where continuously failing metadata deposits are blocking other deposits)

    Requires JSON data dict:
        * func: String - the required function, one of: ("toggle_account" | "toggle_repo_status" | "skip_blocking_note")
        * note_id (for skip_blocking_note only): Int - Notification ID
        * err_id (for skip_blocking_note only): Int - ID of SWORD deposit rec recording notification error

    :param org_id: ID of organisation account
    """
    def _toggle_account():
        """
        Toggle account status On <-> Off
        :return: Dict with status
        """
        if acc.is_repository:
            new_status = acc.repository_data.toggle_status_on_off()
        elif acc.is_publisher:
            new_status = acc.publisher_data.toggle_status_on_off()
        else:
            new_status = None
        acc.update()
        current_app.logger.info(f"Status of {acc.role} account '{acc.org_name}' ({acc.id}) set: '{new_status}'.")
        return {"status": acc.translate_status(new_status)}

    def _toggle_repo_status():
        """
        Toggle Repository account status Failing <-> Succeeding
        :return: Dict with status
        """
        if acc.is_repository:
            new_status = acc.repository_data.toggle_repo_status()
            acc.update()
        else:
            new_status = None
            acc.rollback()
        return {"status": acc.translate_status(new_status)}

    def _skip_blocking_note():
        """
        Set the `last_deposited_note_id` on the repo account to the value of a notification that is repeatedly failing
        to deposit, thus spoofing successful deposit & allowing that notification to be skipped.
        :return: Dict or None
        """
        _validate_json_dict(data_dict, ("note_id", "err_id"))
        note_id = int(data_dict.get("note_id"))
        sword_deposit_err_id = int(data_dict.get("err_id"))
        # If repository account, currently failing and the provided note_id is greater than last-successfullly-deposited-note-id
        if acc.is_repository and acc.status == FAILING and note_id:
            repo_data = acc.repository_data
            if  note_id > repo_data.last_deposited_note_id:
                # Check that specified error ID corresponds to Account & Notification, & it records a metadata error
                sword_deposit = SwordDepositRecord.pull(sword_deposit_err_id, raise_if_none=True)
                if sword_deposit.repository == acc.id and sword_deposit.notification == note_id and sword_deposit.metadata_status == FAILED:
                    # Set `last_deposited_note_id` to the value of note_id - this spoofs successful deposit of that failing notification
                    repo_data.last_deposited_note_id = note_id
                    acc.status = OKAY
                    acc.update()

                    ## Generate an email message to the Repo account ##

                    doi = sword_deposit.doi or ""   # Slightly more efficient to get DOI from SwordDepositRecord
                    # First convert XML/HTML tags in sword-error-message to HTML safe (displayable) values, then truncate if necessary
                    sword_error_text = truncate_string(encode_tags_adjust_whitespace(sword_deposit.error_message), 8000, append=" [ERROR TRUNCATED]")
                    email_msg = f'<p>Publications Router has repeatedly failed to deposit the item detailed below into your repository. No further attempts will be made as the error appears to be insurmountable.</p><blockquote><b>Error Text</b><br><br>{sword_error_text}</blockquote><p>You may wish to create an entry manually.</p><h2>Item Details</h2><p><b>Router ID</b>: {note_id}</p><p><b>DOI</b>: <a href="https://doi.org/{doi}">{doi}</a></p>'

                    # Retrieve offending notification (if it is still in the database - it will have been deleted after 90 days)
                    note = RoutedNotification.pull(note_id)
                    if note is None:    # Notification not found - presumably over 90 days old & deleted
                        email_msg += f'<p><b>Metadata</b>:  No longer available as the record is over 90 days old & has been deleted</p>'
                    else:
                        outgoing_note = note.make_outgoing()    # Conversion is necessary as it adjusts the links list
                        email_msg += f'<p><b>Source</b>: {outgoing_note.provider_agent}</p><p><b>Title</b>: {outgoing_note.article_title}</p>'
                        # Get best link for downloading Article zip package or PDF
                        download_link, is_package = outgoing_note.get_download_link(repo_data.packaging, acc.api_key)
                        if download_link:
                            email_msg += f'<p><b>Download</b>: <a href="{download_link}">{"Zip file containing article" if is_package else "Article PDF"}</a></p>'
                        view_note_url = url_for(
                            'account.notifications', repo_uuid=acc.uuid, note_id=note_id, api_key=acc.api_key,
                            _external=True, _scheme=current_app.config["PREFERRED_URL_SCHEME"])
                        email_msg += f'<p><b>Metadata</b>: <a href="{view_note_url}">View metadata</a> in JSON format extracted by Router (click the <u>data</u> link in the last column on the displayed page)</p>'

                    # current_app.logger.debug(f"Email msg for insertion: |{email_msg}|")
                    to_list, cc_list = acc.send_email(
                        f"PubRouter failing to deposit item into your repository",
                        email_msg,
                        to=acc.TECHS,  # Prefer tech contact emails, if absent default to contact_email (as a list)
                        email_template="mail/contact.html",
                        save_acc_email_rec=True
                    )
                    msg = f"Failing notification ID {note_id} has been skipped"
                    if to_list:
                        msg += f" and an email sent To: {'; '.join(to_list)}"
                        if cc_list:
                            msg += f", CC: {'; '.join(cc_list)}"

                    current_app.logger.info(f"For account '{acc.org_name}' ({acc.id}); {msg}.")

                    return {"status": acc.translate_status(OKAY), "msg": msg}       # RETURN

                else:
                    errs = []
                    if sword_deposit.repository != acc.id:
                        errs.append(f"is not for the specified institution (ID {acc.id})")
                    if sword_deposit.notification != note_id:
                        errs.append(f"is not for the specified notification (ID {note_id})")
                    if sword_deposit.metadata_status != FAILED:
                        errs.append(f"is not for a metadata failure")
                    error = f"The specified SWORD deposit record (ID {sword_deposit_err_id}) {' and '.join(errs)}"
            else:
                error = f"The specified notification (ID {note_id}) has previously been deposited or skipped"
        else:
            error = ""
            errs = []
            if not acc.is_repository:
                errs.append(f"is not an institution (repository)")
            if acc.status != FAILING:
                errs.append(f"has status ({acc.org_status()}) that is not failing")
            if errs:
                error = f"The specified account ({acc.org_name}, ID {acc.id}) {' and '.join(errs)} "
            if not note_id:
                error += f"Notification ID ({note_id}) is unacceptable"

        raise Exception(error)

    data_dict = request.json
    func_name = data_dict.pop("func")   # Remove `func` element from dict
    func = locals().get(f"_{func_name}")  # Select appropriate function defined above by name
    if func:
        acc = AccOrg.pull(org_id, for_update=True)
        if acc:
            try:
                # Execute required function & send JSON response
                return jsonify(func())
            except Exception as e:
                acc.rollback()
                err_str = str(e)
        else:
            err_str = f"Account with ID '{org_id}' not found"
    else:
        err_str = f"Function '{func_name}' missing or not recognised"
    # If we get this far then an error has occurred
    current_app.logger.error(f"In `admin_ajax` - Function '{func_name}' failed with error: {err_str}")
    json_abort(400, err_str)
    return None

# Update Repository details (Repository name, software, SWORD account etc)
@blueprint.route('/<org_uuid>/repoinfo', methods=['POST'])
@org_user_or_admin_org__gui()
def repoinfo(org_uuid, curr_user=None, cu_org_acc=None):
    """
        UPDATE Repository Connection Settings
    :param org_uuid: UUID of organisation to be displayed
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    """
    org_acc = _get_org_acc_by_uuid(org_uuid, for_update=True)
    form_repo_settings = RepoSettingsForm(request.form)
    if form_repo_settings.validate_it(org_acc.has_live_date()):

        repo_data = org_acc.repository_data
        repo_data.repository_url = form_repo_settings.repository_url.data
        repo_data.repository_name = form_repo_settings.repository_name.data
        repo_data.repository_software = form_repo_settings.repository_software.data

        repo_data.add_sword_credentials(
            form_repo_settings.sword_username.data,
            form_repo_settings.sword_password.data,
            form_repo_settings.sword_collection.data
        )
        xml_format = form_repo_settings.xml_format.data
        packaging = form_repo_settings.packaging.data

        # if we have do not have a packaging option but do have an xml format, take a default
        if not packaging and xml_format:
            packaging = current_app.config["REPOSITORY_PACKAGING_OPTIONS"][xml_format][0][0]

        repo_data.repository_xml_format = xml_format
        # Add packaging that will be in comma separated string if more than one packaging type
        repo_data.packaging = packaging

        repo_data.repository_queue = form_repo_settings.target_queue.data if repo_data.is_eprints() else ""

        org_acc.update()
        flash('Your repository details have been updated.', "success")
        return redirect(url_for('.disp_org_acc', org_uuid=org_uuid))
    else:
        org_acc.rollback()
        flash("Connection setting update failed.", 'error')
        return _disp_org_acc(org_acc, curr_user, cu_org_acc, form_repo_settings=form_repo_settings)


# Change repository account notification sources (i.e. particular harvesters & publishers)
@blueprint.route('/<org_uuid>/change_sources', methods=['POST'])
@org_user_or_admin_org__gui()
def change_sources(org_uuid, curr_user=None, cu_org_acc=None):
    """
    :param org_uuid: UUID of organisation to be displayed
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    """
    acc = _get_org_acc_by_uuid(org_uuid, for_update=True)
    excluded_ids_str = request.values.get('excluded_provider_ids')
    acc.repository_data.excluded_provider_ids = excluded_ids_str.split(',') if excluded_ids_str else []
    acc.update()
    flash('Your notification sources have been saved.', "success")
    return redirect(url_for('.disp_org_acc', org_uuid=org_uuid))


# Repository SWORD deposit history
@blueprint.route("/<repo_uuid>/sword_history", methods=["GET"])
@org_user_or_admin_org__gui("repo_uuid")
def sword_deposit_history(repo_uuid=None, curr_user=None, cu_org_acc=None):
    """
    Returns deposit submissions for the given repo.

    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    :param repo_uuid: Repo UUID to check if we're an admin, otherwise the current repo or abort with a 401.
    """
    kwargs = _deposit_record_history_to_template_variables(
        cu_org_acc,
        "repository",
        repo_uuid,
        SwordDepositRecord.aggregate_sword_deposit_daily,
        link_template="/account/{}/sword_history",
        from_date_default_days_offset=10,
        content_href=current_app.config.get("API_URL") + "/{}/content?api_key="
    )
    if kwargs:
        kwargs['curr_user_acc'] = curr_user
        kwargs['title'] = 'SWORD Deposit History'
        kwargs['stored_months'] = retained_months("sword_deposit")
        response = render_template('account/sword_history.html', **kwargs)
    else:
        response = ''
    return response

def _info_dict_to_csv_file(info_dict):
    """
    Create CSV file using contents of info_dict:
    {
        "uuid": account.uuid,
        "org_name": account.org_name,
        "data_iterable": data_iterable,
        "col_headings": col_headings
    }
    :param info_dict: Dict = see above
    :return: Returns send_file(...)
    """
    row_count, bytes_io_obj = create_in_memory_csv_file(data_context_mgr_iterable=info_dict.get("data_iterable"),
                                                        heading_row=info_dict["col_headings"])
    filename = info_dict["org_name"].replace(" ", "_")

    return send_file(
        bytes_io_obj,
        mimetype='text/csv',
        download_name=f"{filename}.csv",
        as_attachment=True
    )

# Repository SWORD deposit history CSV file
@blueprint.route("/<repo_uuid>/sword_history/csv", methods=["GET"])
@org_user_or_admin_org__gui("repo_uuid")
def csv_sword_deposit_history(repo_uuid=None, curr_user=None, cu_org_acc=None):
    """
    Creates a downloadable CSV for any history range and page.

    :param repo_uuid: Repo UUID to check if an admin, otherwise None (will return a 400 if not admin)
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    :return: Downloadable CSV version of deposit history data
    """
    info_dict = _deposit_record_history_to_template_variables(
        cu_org_acc,
        "repository",
        repo_uuid,
        SwordDepositRecord.recs_scroller_for_csv_file,
        from_date_default_days_offset=10,
        page_required=False,
        display_error=False
    )
    return _info_dict_to_csv_file(info_dict)

def _since_date_doi_note_id_request_args(request_args, link):
    """
    Obtain Since-date and DOI from Request args (IF PROVIDED) and return them together with updated link value
    :param request_args: DICT Request Args
    :param link: String - URL which will have argument appended

    :return: Tuple (since-date-obj, since-date-string, doi-string, search-DOI-string, link-string)
    """
    since_date_obj = None
    since_date_str = ""
    search_doi = None
    note_id = None

    # Process supplied arguments
    doi = request_args.get("doi", "")
    if doi:
        # If DOI starts with domain prefix, we strip it
        has_prefix = match_doi_prefix.match(doi)
        if has_prefix:
            # Set doi to the value with prefix stripped off
            doi = has_prefix.group(1)
        # Otherwise, iIf DOI doesn't start with wild card and doesn't start with "10." then add wildcard
        elif not doi_starts_with_regex.match(doi):
            doi = "*" + doi
        search_doi = doi.replace("*", "%")  # Convert to a MySQL search string for use in ` LIKE '...' `
        link += f"doi={doi}"
    else:
        note_id = request_args.get("note_id", "")
        if note_id:
            link += f"note_id={note_id}"
        else:
            since_date_str = request_args.get("since")
            if since_date_str:
                since_date_obj = any_to_datetime(since_date_str)    # Sets None if invalid date string
            if not since_date_obj:
                since_date_obj = _relative_to_today(months=-retained_months())
            since_date_str = since_date_obj.strftime("%Y-%m-%d")  # date string as "YYYY-MM-DD" format
            link += f"since={since_date_str}"

    return since_date_obj, since_date_str, doi, search_doi, note_id, link

# Repository Notification history
@blueprint.route('/<repo_uuid>/notifications', methods=["GET"])
@org_user_or_admin_org__gui("repo_uuid")
def notifications(repo_uuid, curr_user=None, cu_org_acc=None):
    """
    Display notifications matched to a particular repository.
    URL parameters include:
        since (since-date)
        doi (DOI to search for)
        note_id (a particular notification ID)
    :param repo_uuid: String - UUID for repository
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    :return:
    """
    def notifications_with_provenance(since_datetime=None, note_id=None, search_doi=None, page=None, page_size=None, repo_id=None, order="asc"):
        """
        Obtain a list of notifications plus associated match provenance which meet the criteria specified by the
        parameters. These are returned as a list of dicts.  IMPORTANT: if search_doi is set, then since_datetime
        and since_id are ignored.

        :param since_datetime: Datetime - date YYYY-MM-DD, for the earliest notification date requested
        :param note_id: Integer - Return notification with ID matching this value
        :param search_doi: String - Return notifications that match supplied DOI (or partial DOI) - can contain "%" wild card(s)
        :param page: page number in result set to return
        :param page_size: number of results to return in this page of results
        :param repo_id: the id of the repository whose notifications to return.
        :param order: The listing order: asc or desc

        :return: List of Tuples (OutgoingNotifications, MatchProvenance)
        """
        # Set up values in MatchProvenance class so `recreate_json_dict_from_rec()` works as expected.
        MatchProvenance.set_all_cols()
        current_api_version = current_app.config.get('API_VERSION')
        def format_rec(rec_tuple):
            """
            Callback function to format the raw record tuple returned by bespoke queries
            """
            rec = list(rec_tuple)
            # Split the record into Notification and Match Provenance field lists
            note_rec = rec[:15]
            match_prov_rec = rec[15:]
            # Now recreate the original dicts for Notification and Match-provenance
            note_dict = RoutedNotification.recreate_json_dict_from_rec(note_rec)
            match_prov_dict = MatchProvenance.recreate_json_dict_from_rec(match_prov_rec)
            # Replace match-provenance type string by "human readable" string
            first_prov = match_prov_dict.get("provenance")[0]
            # format our source_field to be the human readable equivalent of our internal metadata name
            first_prov["source_field"] = MatchProvenance.user_readable_match_param_type(first_prov["source_field"])
            return RoutedNotification(note_dict).make_outgoing(current_api_version), MatchProvenance(match_prov_dict)

        # limit_offset = [Int: num-rows, Int: offset)]
        limit_offset = RoutedNotification.calc_limit_offset_param(page, page_size)
        # Each row returned (as a tuple) contains all columns in notification table + match_provenance table
        # (These are defined by the Bespoke SELECT query "bspk_notes_with_prov" or "bspk_notes_like_doi_with_prov"
        # or "bspk_notes_equal_doi_with_prov" in mysql_dao.py).
        if search_doi:
            pull_name = "bspk_notes_{}_doi_with_prov".format("like" if "%" in search_doi else "equal")
            scroller = RoutedNotification.reusable_scroller_obj(
                repo_id, search_doi, pull_name=pull_name, limit_offset=limit_offset, order_by=order,
                 rec_format=format_rec, scroll_num=NOTES_WITH_PROV_DOI_SCROLL_NUM)
        elif note_id:
            # This should return 1 record at most
            scroller = RoutedNotification.reusable_scroller_obj(
                repo_id, note_id, pull_name="bspk_one_note_with_prov", limit_offset=limit_offset, order_by=None,
                 rec_format=format_rec, scroll_num=NOTES_WITH_PROV_NOTEID_SCROLL_NUM)
        else:
            scroller = RoutedNotification.reusable_scroller_obj(
                repo_id, since_datetime, pull_name="bspk_notes_with_prov", limit_offset=limit_offset, order_by=order,
                 rec_format=format_rec, scroll_num=NOTES_WITH_PROV_DATE_SCROLL_NUM)
        with scroller:
            note_match_prov_obj_tuple_list = [row_tuple for row_tuple in scroller]

        return note_match_prov_obj_tuple_list

    # If current org-user is Admin, then we want to retrieve Org Account that the Admin user selected (will abort
    # with 404 if not found); otherwise we just use the user's parent Org Account
    org_acc = _get_org_acc_by_uuid(repo_uuid) if cu_org_acc.is_super and cu_org_acc.uuid != repo_uuid else cu_org_acc
    repo_id = org_acc.id
    link = f"/account/{org_acc.uuid}/notifications?"

    since_date_obj, since_date_str, doi, search_doi, note_id, link = _since_date_doi_note_id_request_args(request.args, link)
    page, page_size = get_page_details_from_request(request.args)
    try:
        notification_matchdata_tuples = notifications_with_provenance(
            since_date_obj, note_id=note_id, search_doi=search_doi, page=page, page_size=page_size, repo_id=repo_id, order="desc")
        if note_id:     # Retrieving a single notification
            num_of_pages = 1    #
        else:
            num_notifications_for_ac = RoutedNotification.count(repo_id=repo_id, since_date=since_date_obj, search_doi=search_doi)
            num_of_pages = calc_num_of_pages(page_size, num_notifications_for_ac)
    except ParameterException:
        notification_matchdata_tuples = []
        num_of_pages = 0

    return render_template('/account/note_history.html',
                           curr_user_acc=curr_user,
                           notification_matchdata_tuples=notification_matchdata_tuples,
                           num_of_pages=num_of_pages,
                           page_num=page,
                           link=link,
                           since_date=since_date_str,
                           doi=doi,
                           uuid=org_acc.uuid,
                           org_name=org_acc.org_name,
                           title='Notification History',
                           stored_months=retained_months("notification"))


# Repository Matching parameters page
@blueprint.route("/<repo_uuid>/match_params", methods=["GET"])
@org_user_or_admin_org__gui("repo_uuid")
def view_match_params(repo_uuid, curr_user=None, cu_org_acc=None):
    """
    :param repo_uuid: UUID of organisation to be displayed
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    """
    if current_app.config.get("LOG_DEBUG"):
        current_app.logger.debug(curr_user.uuid + " " + request.method + " to config route")

    # If current org-user is Admin, then we want to retrieve Org Account that the Admin user selected (will abort
    # with 404 if not found); otherwise we just use the user's parent Org Account
    org_acc = _get_org_acc_by_uuid(repo_uuid) if cu_org_acc.is_super and cu_org_acc.uuid != repo_uuid else cu_org_acc
    if not org_acc.is_repository:
        _abort(400, "Account is not an institution repository.")

    matching_params = AccRepoMatchParams.pull(org_acc.id)

    return render_template(
        'account/match_params.html',
        curr_user_acc=curr_user,
        org_acc=org_acc,
        matching_params=matching_params,
        has_archived_params=AccRepoMatchParamsArchived.count_archived_match_param_pkids_for_org(org_acc.id),
        title='View Matching Parameters'
    )


# Update Matching Params via CSV file or from JSON structure at a specified URL endpoint
# POST: Replace current matching params by new ones; PATCH: Update current matching params by adding new ones.
@blueprint.route('/<org_uuid>/match_params', methods=['POST', 'PATCH'])
@org_user_or_admin_org__gui()
def set_match_params(org_uuid, curr_user=None, cu_org_acc=None):
    """
    :param org_uuid: UUID of organisation to be displayed
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    """
    # The form submits the following params: file = filename, url = URL to either JSON or a CSV file

    def _config_changed_html_snippet(changed_params, matching_config):
        lookup = {
            "name_variants": "Name Variants",
            "org_ids": "Organisation identifiers",
            "domains": "Domains",
            "postcodes": "Postcodes",
            "grants": "Grant Numbers",
            "emails": "Author Emails",
            "orcids": "ORCIDs"
        }
        snippet_list = [f'<li>{lookup[k]} ({len(matching_config[k])})</li>' for k in changed_params]
        return f"<br><br><p>Parameters loaded (count):</p><ul>{''.join(snippet_list)}</ul>"

    # If current org-user is Admin, then we want to retrieve Org Account that the Admin user selected (will abort
    # with 404 if not found); otherwise we just use the user's parent Org Account
    org_acc = _get_org_acc_by_uuid(org_uuid) if cu_org_acc.is_super and cu_org_acc.uuid != org_uuid else cu_org_acc
    try:
        add_params = request.method == 'PATCH'
        file_name = None
        params_loaded = None
        # If a URL is submitted from the form - could be a URL to JSON or a CSV file.
        url = request.values.get('url')
        if url:
            # Fetch content using URL
            r = requests.get(url)
            try:
                # Set matching params if the content retrieved from URL is JSON
                # note that r.json() will raise an exception otherwise
                params_loaded, redundancies, matching_params = AccRepoMatchParams.update_match_params(
                    org_acc.id, org_acc.org_name, org_acc.uuid, jsoncontent=r.json(), add=add_params)
            except Exception:
                # response could not be converted to JSON, so assume URL was to a CSV file

                # extract filename from the URL
                file_name = url.split('?')[0].split('#')[0].split('/')[-1]
                # Convert retrieved content into a filestream
                strm = BytesIO(r.content)
        else:
            # No URL, so retrieve filename
            file_name = request.files['file'].filename
            strm = request.files['file']

        # If params to be loaded from CSV file or JSON file
        if file_name:
            if file_name.endswith('.csv'):
                params_loaded, redundancies, matching_params = AccRepoMatchParams.update_match_params(
                    org_acc.id, org_acc.org_name, org_acc.uuid, csvfile=strm, add=add_params)
            elif file_name.endswith('.json'):
                # json_str = strm.read().decode("utf-8")
                params_loaded, redundancies, matching_params = AccRepoMatchParams.update_match_params(
                    org_acc.id, org_acc.org_name, org_acc.uuid, jsoncontent=load(strm), add=add_params)

        # returns None upon failure, a list upon success (empty or otherwise)
        if params_loaded is not None:
            changes_html = _config_changed_html_snippet(params_loaded, matching_params.matching_config)
            flash(f"Your matching parameters have been updated & the previous version archived." + changes_html, "success+html")
            # if there is a list of length > 0 (there are actual removed redundancies to report to the user)
            if redundancies:
                # special flash (category: "list") which displays an expandable list of redundancies removed, with a
                # special header, included html partial and maximum list length
                # See src/router/jper/templates/_flash.html for implementation of special flash mechanism
                flash(
                    {
                        "partial_name": "account/partial/redundancy_info.html",
                        "listdata": redundancies,
                        "header_data": "Some redundant match parameters were removed during upload, expand for more information.",
                        "max_list_length": 20
                    },
                    "list")
        else:
            err_msg = ('There was an error with your upload; no changes were made. Please check that your file is in '
                       'CSV format with headers consistent with this <a href="/static/csvtemplate.csv" '
                       'target="_blank">template</a> and contains only ASCII characters, then try again. '
                       'If the problem persists please contact XXXX@YYYY.ac.uk')
            flash(err_msg, "error+html")
    except Exception as e:
        # Log a warning with exception-info (stack trace) added
        current_app.logger.warning(f"Problem uploading repo config for acc Id: {org_acc.id} - {org_acc.uuid} ({org_acc.org_name}): {repr(e)}")
        flash(f"There was an error with your upload: {str(e)}.  (No changes have been made).", "error+html")
    return redirect(url_for('.view_match_params', repo_uuid=org_uuid))


# Get repository account matching params as CSV file
@blueprint.route("/<org_uuid>/match_params/csv")
@org_user_or_admin_org__gui()
def match_params_as_csv(org_uuid, curr_user=None, cu_org_acc=None):
    """
    Create a CSV file from the repository's matching parameters and return it to the user.
    :param org_uuid: UUID of organisation to be displayed
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    """
    def data_row_generator(matching_params):
        """
        Generates rows of data for outputting to CSV file
        :param matching_params: Matching parameters Object
        :return:
        """
        def pop_and_add_to_list(row_list, list_to_pop):
            """
            Pop from one list and add to another list - if there is nothing left in the list, don't add anything.

            :param row_list: List to ADD data to
            :param list_to_pop: List used to retrieve the value
            :return: Boolean - True if value found; False no value
            """
            try:
                value = list_to_pop.pop()
                row_list.append(value)
                return True
            except IndexError:
                # There is nothing left in the list - the other lists may still have values though, so don't throw error
                row_list.append(None)
                return False

        if matching_params:
            name_vars = matching_params.name_variants
            domains = matching_params.domains
            postcodes = matching_params.postcodes
            grants = matching_params.grants
            orcids = matching_params.author_orcids
            emails = matching_params.author_emails
            org_ids = matching_params.org_ids

            while True:
                next_row = []
                data_found = False  # Will be set to True if any of following calls to pop_and_add_to_list returns True
                data_found |= pop_and_add_to_list(next_row, name_vars)
                data_found |= pop_and_add_to_list(next_row, domains)
                data_found |= pop_and_add_to_list(next_row, postcodes)
                data_found |= pop_and_add_to_list(next_row, grants)
                data_found |= pop_and_add_to_list(next_row, orcids)
                data_found |= pop_and_add_to_list(next_row, emails)
                data_found |= pop_and_add_to_list(next_row, org_ids)
                # if we do have data, write the row into the csv
                if data_found:
                    yield next_row
                else:
                    # If we don't have any data left, just break out of the loop
                    break
        return None

    # If current org-user is Admin, then we want to retrieve Org Account that the Admin user selected (will abort
    # with 404 if not found); otherwise we just use the user's parent Org Account
    org_acc = _get_org_acc_by_uuid(org_uuid) if cu_org_acc.is_super and cu_org_acc.uuid != org_uuid else cu_org_acc

    # Retrieve account's matching params
    matching_params = AccRepoMatchParams.pull(org_acc.id)

    row_count, bytes_io_obj = create_in_memory_csv_file(
        data_iterable=data_row_generator(matching_params),
        heading_row=["Name Variants", "Domains", "Postcodes", "Grant Numbers", "ORCIDs", "Author Emails", "Organisation Identifiers"]
    )

    # Get the repo account so we can add the username as part of the filename
    account_org_name = org_acc.org_name.replace(" ", "_")

    return send_file(
        bytes_io_obj,
        mimetype='text/csv',
        download_name=f"Matching_Parameters_{account_org_name}.csv",
        as_attachment=True
    )


# Get repository account matching params as JSON file
@blueprint.route("/<org_uuid>/match_params/json")
@org_user_or_admin_org__gui()
def match_params_as_json(org_uuid, curr_user=None, cu_org_acc=None):
    """
    Create a JSON text file from the repository's matching parameters and return it to the user.
    :param org_uuid: UUID of organisation to be displayed
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    """
    # If current org-user is Admin, then we want to retrieve Org Account that the Admin user selected (will abort
    # with 404 if not found); otherwise we just use the user's parent Org Account
    org_acc = _get_org_acc_by_uuid(org_uuid) if cu_org_acc.is_super and cu_org_acc.uuid != org_uuid else cu_org_acc

    # Retrieve account's matching params
    matching_params = AccRepoMatchParams.pull(org_acc.id)
    json_str = dumps(matching_params.matching_config, indent=4) if matching_params else ""
    # Get the repo account so we can add the username as part of the filename
    account_org_name = org_acc.org_name.replace(" ", "_")
    return send_file(
        BytesIO(json_str.encode("utf-8")),
        mimetype='application/json',
        download_name=f"Matching_Parameters_{account_org_name}.json",
        as_attachment=True
    )


@blueprint.route("/<org_uuid>/archived_match_params/<pkid>/json")
@admin_org_only__gui
def archived_match_params_json(org_uuid, pkid, curr_user=None, cu_org_acc=None):
    """
    Create a JSON text file from the repository's matching parameters and return it to the user.
    :param org_uuid: UUID of organisation to be displayed
    :param pkid: PKID of archived match params
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    """
    # If current org-user is Admin, then we want to retrieve Org Account that the Admin user selected (will abort
    # with 404 if not found); otherwise we just use the user's parent Org Account
    org_acc = _get_org_acc_by_uuid(org_uuid) if cu_org_acc.is_super and cu_org_acc.uuid != org_uuid else cu_org_acc

    # Retrieve archived matching params
    archived_match_params = AccRepoMatchParamsArchived.pull(pkid)
    if archived_match_params:
        if archived_match_params.id != org_acc.id:
            flash(f"Archived parameters with PKID {pkid} do not exist for the specified organisation", "error")
            return redirect(request.referrer)
    else:
        flash(f"Archived parameters with PKID {pkid} not found", "error")
        return redirect(request.referrer)

    json_str = dumps(archived_match_params.matching_config, indent=4)
    acc_org_name = org_acc.org_name.replace(" ", "_")
    archived_str = archived_match_params.archived_datetime_str('%d-%m-%Y_%Hh%Mm%Ss')
    return send_file(
        BytesIO(json_str.encode("utf-8")),
        mimetype='application/json',
        download_name=f"Matching_Parameters_Archived_{archived_str}_{acc_org_name}.json",
        as_attachment=True
    )


@blueprint.route("/<repo_uuid>/revert_match_params/<pkid>", methods=["POST"])
@admin_org_only__gui
def revert_match_params(repo_uuid, pkid=None, curr_user=None, cu_org_acc=None):
    # If current org-user is Admin, then we want to retrieve Org Account that the Admin user selected (will abort
    # with 404 if not found); otherwise we just use the user's parent Org Account
    org_acc = _get_org_acc_by_uuid(repo_uuid) if cu_org_acc.is_super and cu_org_acc.uuid != repo_uuid else cu_org_acc
    org_id = org_acc.id
    # Retrieve archived matching params
    match_params_to_restore = AccRepoMatchParamsArchived.pull(pkid)
    if match_params_to_restore:
        if match_params_to_restore.id != org_id:
            flash(f"Archived parameters with PKID {pkid} do not exist for the specified organisation", "error")
            return redirect(request.referrer)
    else:
        flash(f"Archived parameters with PKID {pkid} not found", "error")
        return redirect(request.referrer)

    replaced_params_archive = match_params_to_restore.revert_to_these_params()

    log_msg = f"Reverted matching parameters for Repo account ID: '{org_acc.org_name}' ({org_id}) to those with PKID {pkid}.\n  Previous matching params archived with PKID: {replaced_params_archive.pkid}."
    flash_msg = f"Matching parameters reverted to those archived on {match_params_to_restore.archived_datetime_str()} (pkid {pkid})."
    subject = "Reverting matching params"

    # If we just restored a set of parameters WITHOUT RegEx overwriting params that HAD RegEx
    if replaced_params_archive.has_regex and not match_params_to_restore.has_regex:
        regex_note = "  NOTE: The previous params had RegEx, but the reverted params do not."
        current_app.logger.warning(f"{log_msg}\n{regex_note}",
                                   extra={"mail_it": True, "subject": subject + " - RegEx overwritten!"})
        flash(f"{flash_msg}<br/><br/>{regex_note}", "success+html")
    else:
        current_app.logger.info(log_msg, extra={"mail_it": True, "subject": subject})
        flash(flash_msg, "success+html")

    return redirect(request.referrer)


@blueprint.route("/<repo_uuid>/compare_match_params", methods=["GET"])
@admin_org_only__gui
def compare_match_params(repo_uuid, curr_user=None, cu_org_acc=None):
    """
    :param repo_uuid: UUID of organisation to be displayed
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    """
    if current_app.config.get("LOG_DEBUG"):
        current_app.logger.debug(curr_user.uuid + " " + request.method + " to config route")

    # If current org-user is Admin, then we want to retrieve Org Account that the Admin user selected (will abort
    # with 404 if not found); otherwise we just use the user's parent Org Account
    org_acc = _get_org_acc_by_uuid(repo_uuid) if cu_org_acc.is_super and cu_org_acc.uuid != repo_uuid else cu_org_acc
    if not org_acc.is_repository:
        _abort(400, "Account is not an institution repository.")

    org_id = org_acc.id
    prev_params = AccRepoMatchParamsArchived.list_archived_match_param_pkids_for_org(org_id)

    get_pkid = archived_match_params = None
    prev_pkid = request.args.get("prev_param")
    if prev_pkid:
        get_pkid = int(prev_pkid)
        for id_, _, _ in prev_params:
            if prev_pkid == id_:
                get_pkid = prev_pkid
                break
        if not get_pkid:
            flash(f"Archived parameters with PKID {prev_pkid} do not exist for this organisation", "error")
    if not get_pkid and prev_params:
        # Get most recent archived version
        get_pkid = prev_params[0][0]
    if get_pkid:
        archived_match_params = AccRepoMatchParamsArchived.pull(get_pkid)

    matching_params = AccRepoMatchParams.pull(org_id)

    compare_form = CompareMatchParamsForm(archived_versions=prev_params, selected=get_pkid)

    return render_template(
        'account/match_params_compare.html',
        curr_user_acc=curr_user,
        org_acc=org_acc,
        compare_form=compare_form,
        matching_params=matching_params,
        archived_params=archived_match_params,
        title='Compare Matching Parameters'
    )


@blueprint.route("/match_params_summary", methods=["GET"])
@admin_org_only__gui
def match_params_summary(curr_user=None, cu_org_acc=None):
    """
    List Accounts that include regex in their match params
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    """
    min_status = int(request.args.get("status", 1))
    return render_template(
        'account/match_params_summary.html',
        curr_user_acc=curr_user,
        ac_data=AccRepoMatchParams.get_summary_info(min_status=min_status),
        title="Summary of Repository Matching Parameters",
        only_on=min_status == 1
    )


# Update repository notification Max age value
@blueprint.route("/<org_uuid>/update_other_match", methods=["POST"])
@org_user_or_admin_org__gui()
def update_other_match_params(org_uuid, curr_user=None, cu_org_acc=None):
    """
    :param org_uuid: UUID of organisation to be displayed
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    """
    acc = _get_org_acc_by_uuid(org_uuid, for_update=True)
    acc_repo_data = acc.repository_data
    form = MatchSettingsForm(request.form, data={"pub_years": acc_repo_data.max_pub_age})

    if form.validate():
        acc_repo_data.max_pub_age = form.pub_years.data
        acc.update()
        flash("Successfully updated maximum age", "success")
    else:
        acc.rollback()
        flash("Maximum age must be an integer between 1 and 100, or blank.", "error")

    return redirect(url_for('.disp_org_acc', org_uuid=org_uuid))


# Update information related to publisher testing
@blueprint.route('/<org_uuid>/update_repo_duplicates', methods=['POST'])
@org_user_or_admin_org__gui()
def update_repo_duplicates(org_uuid, curr_user=None, cu_org_acc=None):
    """
    Update Publisher Test info.

    :param org_uuid: UUID of organisation to be displayed
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    :return: Either redirect to User account page (if no errors) or redisplay User account page (if errors)
    """
    org_acc = _get_org_acc_by_uuid(org_uuid, for_update=True)
    form_repo_duplicates = RepoDuplicatesForm(request.form)
    if form_repo_duplicates.validate():
        # If validated OK
        repo_data = org_acc.repository_data
        repo_data.dups_level_pub = form_repo_duplicates.dups_level_pub.data
        repo_data.dups_level_harv = form_repo_duplicates.dups_level_harv.data
        ### TODO: INCLUDE in FUTURE RELEASE
        # repo_data.dups_emails = form_repo_duplicates.dups_emails.email_list
        # repo_data.dups_meta_format = form_repo_duplicates.dups_meta_format.data
        org_acc.update()
        flash('Your duplicate handling settings have been updated.', 'success')
        return redirect(url_for('.disp_org_acc', org_uuid=org_uuid))
    else:
        org_acc.rollback()
        flash(f"Update failed: {form_repo_duplicates.error_summary()}. Scroll down for details.", 'error')
        return _disp_org_acc(org_acc, curr_user, cu_org_acc, form_repo_duplicates=form_repo_duplicates)


# Update information related to publisher reports
@blueprint.route('/<org_uuid>/update_pub_reports', methods=['POST'])
@org_user_or_admin_org__gui()
def update_pub_reports(org_uuid, curr_user=None, cu_org_acc=None):
    """
    Update Publisher Reports info.

    :param org_uuid: UUID of organisation to be displayed
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    :return: Either redirect to User account page (if no errors) or redisplay User account page (if errors)
    """
    org_acc = _get_org_acc_by_uuid(org_uuid, for_update=True)
    pub_data = org_acc.publisher_data
    form_pub_reports = PubReportsForm(request.form, data=pub_data.get_report_data_for_form())
    if form_pub_reports.validate():
        # If validated OK
        pub_data.report_format = form_pub_reports.report_format.data
        pub_data.report_emails = form_pub_reports.report_emails.email_list
        org_acc.update()
        flash('Your report settings have been updated.', 'success')
        return redirect(url_for('.disp_org_acc', org_uuid=org_uuid))
    else:
        org_acc.rollback()
        flash(f"Update failed: {form_pub_reports.error_summary()}. Scroll down for details.", 'error')
        return _disp_org_acc(org_acc, curr_user, cu_org_acc, form_pub_reports=form_pub_reports)


# Update information related to publisher testing
@blueprint.route('/<org_uuid>/update_pub_test', methods=['POST'])
@org_user_or_admin_org__gui()
def update_pub_test(org_uuid, curr_user=None, cu_org_acc=None):
    """
    Update Publisher Test info.

    :param org_uuid: UUID of organisation to be displayed
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    :return: Either redirect to User account page (if no errors) or redisplay User account page (if errors)
    """
    org_acc = _get_org_acc_by_uuid(org_uuid, for_update=True)
    pub_data = org_acc.publisher_data
    form_pub_testing = PubTestingForm(request.form,
                                      data=pub_data.get_test_data_dict_for_form(),
                                      disable_fields=_pub_test_disable_fields(pub_data, cu_org_acc.is_super))
    if form_pub_testing.validate():
        # If validated OK
        pub_data.test_type = form_pub_testing.test_type.data
        pub_data.test_emails = form_pub_testing.test_report_emails.email_list

        # Starting testing for first time
        if not pub_data.test_start and form_pub_testing.start_checkbox.data:
            # Set start to today's date
            pub_data.test_start = pub_data.ymd_date_str_from_date_obj(datetime.today())
            pub_data.in_test = True
            current_app.logger.info(f"Auto-testing STARTED for publisher '{org_acc.org_name}' ({org_acc.id}).")

        # Testing ended checkbox is ticked
        if form_pub_testing.end_checkbox.data:
            # If currently testing
            if pub_data.in_test:
                pub_data.end_testing()
                current_app.logger.info(f"Auto-testing ENDED for publisher '{org_acc.org_name}' ({org_acc.id}).")
        else:  # Testing ended checkbox NOT ticked
            # If test_end was previously set
            if pub_data.test_end:
                pub_data.test_end = None
                pub_data.in_test = form_pub_testing.start_checkbox.data  # Testing in progress if started otherwise not
                current_app.logger.info(f"Auto-testing RE-STARTED for publisher '{org_acc.org_name}' ({org_acc.id}).")
            # If create notifications checkbox changed
            route_note = form_pub_testing.route_note_checkbox.data
            if pub_data.route_note != route_note:
                current_app.logger.info(
                    f"{'ENABLE' if route_note else 'DISABLE'} notification creation & routing while Auto-testing for publisher '{org_acc.org_name}' ({org_acc.id}).")
                pub_data.route_note = route_note

        org_acc.update()
        flash('Your test settings have been updated.', 'success')
        return redirect(url_for('.disp_org_acc', org_uuid=org_uuid))
    else:
        org_acc.rollback()
        flash(f"Update failed: {form_pub_testing.error_summary()}. Scroll down for details.", 'error')
        return _disp_org_acc(org_acc, curr_user, cu_org_acc, form_pub_testing=form_pub_testing)


# Update Publisher default licence details
@blueprint.route('/<org_uuid>/update_defaults', methods=['POST'])
@org_user_or_admin_org__gui()
def update_defaults(org_uuid, curr_user=None, cu_org_acc=None):
    """
    :param org_uuid: UUID of organisation to be displayed
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    """
    acc = _get_org_acc_by_uuid(org_uuid, for_update=True)
    form_pub_settings = PubSettingsForm(request.form)

    # Do field level validation
    if form_pub_settings.validate():
        pub_data = acc.publisher_data
        pub_data.embargo = form_pub_settings.embargo_duration.data
        pub_data.set_license(form_pub_settings.license_title.data,
                             form_pub_settings.license_type.data,
                             form_pub_settings.license_url.data,
                             form_pub_settings.license_version.data,)
        pub_data.peer_reviewed = form_pub_settings.peer_reviewed.data
        acc.update()
        flash('Your defaults have been updated.', 'success')
        return redirect(url_for('.disp_org_acc', org_uuid=org_uuid))
    else:
        acc.rollback()
        # NB. update of peer_reviewed can never fail validation
        flash('Update of embargo and/or licence failed.', 'error')
        return _disp_org_acc(acc, curr_user, cu_org_acc, form_pub_settings=form_pub_settings)


# Publisher deposit history
@blueprint.route("/<pub_uuid>/deposit_history", methods=["GET"])
@org_user_or_admin_org__gui("pub_uuid")
def deposit_history(pub_uuid=None, curr_user=None, cu_org_acc=None):
    """
    Returns deposit submissions for the given publisher.

    :param pub_uuid: Publisher UUID or abort with a 401.
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    """
    kwargs = _deposit_record_history_to_template_variables(
        cu_org_acc,
        "publisher",
        pub_uuid,
        PublisherDepositRecord.aggregate_pub_deposit_daily,
        link_template="/account/{}/deposit_history"
    )
    if kwargs:
        kwargs['curr_user_acc'] = curr_user
        kwargs['title'] = 'Daily deposit summary'
        kwargs['stored_months'] = retained_months("pub_deposit")
        response = render_template('account/deposit_history.html', **kwargs)
    else:
        response = ''
    return response


# Publisher deposit history CSV file
@blueprint.route("/<pub_uuid>/deposit_history/csv", methods=["GET"])
@org_user_or_admin_org__gui("pub_uuid")
def csv_deposit_history(pub_uuid=None, curr_user=None, cu_org_acc=None):
    """
    Creates a downloadable CSV for any history range and page.

    :param pub_uuid: Publisher UUID to check if an admin, otherwise None (will return a 400 if not admin)
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    :return: Downloadable CSV version of deposit history data
    """
    info_dict = _deposit_record_history_to_template_variables(
        cu_org_acc,
        "publisher",
        pub_uuid,
        PublisherDepositRecord.recs_scroller_for_csv_file,
        page_required=False,
        display_error=False)
    return _info_dict_to_csv_file(info_dict)


repo_id_to_orgname_dict = {}    # Map of Live repository org-ids to org-name

# Publisher article deposit (Notification) history
@blueprint.route('/<pub_uuid>/deposits', methods=["GET"])
@org_user_or_admin_org__gui("pub_uuid")
def deposits(pub_uuid, curr_user=None, cu_org_acc=None):
    """
    Display article notifications matched to a particular PUBLISHER.
    URL parameters include:
        since (since-date)
        doi (DOI to search for)
    :param pub_uuid: String - UUID for publisher
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    :return:
    """
    def notifications_with_repo_names(since_datetime=None, search_doi=None, page=None, page_size=None, pub_id=None, order="asc"):
        """
        Obtain a list of notifications plus associated matched organisation names.

        :param since_datetime: Datetime - date YYYY-MM-DD, for the earliest notification date requested
        :param search_doi: String - Return notifications that match supplied DOI (or partial DOI) - can contain "%" wild card(s)
        :param page: page number in result set to return
        :param page_size: number of results to return in this page of results
        :param pub_id: the id of the publisher whose notifications to return.
        :param order: The listing order: asc or desc

        :return: List of Tuples (OutgoingNotifications, MatchProvenance)
        """
        global repo_id_to_orgname_dict
        if not repo_id_to_orgname_dict:
            # Create map of Live repository org-ids to org-name - we only need to do this ONCE
            repo_id_to_orgname_dict = AccOrg.get_account_id_to_org_names_dict("R", live_test="LT")
        current_api_version = current_app.config.get('API_VERSION')

        def format_rec(rec_tuple):
            """
            Callback function to format the raw record tuple returned by bespoke queries
            :return: Tuple - (RoutedNotification-object, Repo-Names-list)
            """
            repo_names = []
            note_dict = RoutedNotification.recreate_json_dict_from_rec(rec_tuple)
            # Create list of repo_names from the IDs of repositories to which notification has been matched
            for repo_id in note_dict.get("repositories", []):
                repo_name = repo_id_to_orgname_dict.get(repo_id)
                if repo_name:
                    repo_names.append(repo_name)
            return RoutedNotification(note_dict).make_outgoing(current_api_version), repo_names

        # limit_offset = [Int: num-rows, Int: offset)]
        limit_offset = RoutedNotification.calc_limit_offset_param(page, page_size)
        pull_name, params = RoutedNotification._get_pull_name_and_params_list(None, pub_id, None, since_datetime, search_doi)
        scroller = RoutedNotification.reusable_scroller_obj(
            *params, pull_name=pull_name, limit_offset=limit_offset, order_by=order,
            rec_format=format_rec, scroll_num=NOTES_WITH_REPO_NAMES_SCROLL_NUM)
        with scroller:
            note_repo_name_tuple_list = [row_tuple for row_tuple in scroller]

        return note_repo_name_tuple_list

    # If current org-user is Admin, then we want to retrieve Org Account that the Admin user selected (will abort
    # with 404 if not found); otherwise we just use the user's parent Org Account
    org_acc = _get_org_acc_by_uuid(pub_uuid) if cu_org_acc.is_super and cu_org_acc.uuid != pub_uuid else cu_org_acc
    pub_id = org_acc.id
    link = f"/account/{org_acc.uuid}/deposits?"

    since_date_obj, since_date_str, doi, search_doi, note_id, link = _since_date_doi_note_id_request_args(request.args, link)
    page, page_size = get_page_details_from_request(request.args)
    try:
        note_repo_name_tuples = notifications_with_repo_names(
            since_date_obj, search_doi=search_doi, page=page, page_size=page_size, pub_id=pub_id, order="desc")
        num_notifications_for_ac = RoutedNotification.count(pub_id=pub_id, since_date=since_date_obj, search_doi=search_doi)
        num_of_pages = calc_num_of_pages(page_size, num_notifications_for_ac)
    except ParameterException:
        note_repo_name_tuples = []
        num_of_pages = 0

    return render_template('/account/pub_note_history.html',
                           curr_user_acc=curr_user,
                           note_repo_name_tuples=note_repo_name_tuples,
                           num_of_pages=num_of_pages,
                           page_num=page,
                           link=link,
                           since_date=since_date_str,
                           doi=doi,
                           uuid=org_acc.uuid,
                           org_name=org_acc.org_name,
                           title='Matched Deposit History',
                           stored_months=retained_months("notification"))


@blueprint.route('/download_report/<type>/<uuid>/<filename>')
def download_report(type, uuid, filename):
    """
    Send the file
    """
    # attempt to send the file from the calculated directory path and filename
    return send_from_directory(f"{current_app.config['REPORTSDIR']}/{type}/{uuid}", filename)


# Publisher reports
@blueprint.route("/<pub_uuid>/reports", methods=["GET"])
@org_user_or_admin_org__gui("pub_uuid")
def list_publisher_reports(pub_uuid=None, curr_user=None, cu_org_acc=None):
    """
    Lists links to existing publisher report files

    :param pub_uuid: Publisher UUID or abort with a 401.
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    """
    # If current org-user is Admin, then we want to retrieve Org Account that the Admin user selected (will abort
    # with 404 if not found); otherwise we just use the user's parent Org Account
    pub_acc = _get_org_acc_by_uuid(pub_uuid) if cu_org_acc.is_super and cu_org_acc.uuid != pub_uuid else cu_org_acc
    _config = current_app.config
    report_type = _config['PUB_DOI_REPORT']
    # Get list of report files for this publisher
    reports = _get_files_from_dir(f"{_config['REPORTSDIR']}/{report_type}/{pub_uuid}",
                                  ".csv",
                                  sort_desc=True)

    return render_template(
        'account/pub_reports.html',
        curr_user_acc=curr_user,
        report_type=report_type,
        org_name=pub_acc.org_name,
        pub_uuid=pub_uuid,
        reports=reports,
        title="List publisher reports"
    )


# Publisher test history
@blueprint.route("<pub_uuid>/test_history", methods=["GET"])
@org_user_or_admin_org__gui("pub_uuid")
def test_history(pub_uuid=None, curr_user=None, cu_org_acc=None):
    """
    Displays test submission history for the given publisher.

    :param pub_uuid: Publisher uuid or abort with a 401.
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    """
    # If current org-user is Admin, then we want to retrieve Org Account that the Admin user selected (will abort
    # with 404 if not found); otherwise we just use the user's parent Org Account
    pub_acc = _get_org_acc_by_uuid(pub_uuid) if cu_org_acc.is_super and cu_org_acc.uuid != pub_uuid else cu_org_acc

    # pub_acc = AccOrg.pull(pub_uuid, pull_name="uuid")
    if pub_acc is None:
        _abort(404, "Publisher account not found.")
    page, page_size = get_page_details_from_request(request.args)
    test_recs = PubTestRecord.publisher_test_recs(publisher_id=pub_acc.id, page=page, page_size=page_size)
    num_pages = calc_num_of_pages(page_size, PubTestRecord.num_pub_test_recs(publisher_id=pub_acc.id))

    # If user navigated to page via link in email, it will have api_key, which we want to add to the link below
    api_key = request.args.get("api_key", "")
    if api_key:
        api_key = f"&api_key={api_key}"

    response = render_template('account/pub_test_history.html',
                               curr_user_acc=curr_user,
                               title=f"Test History for {pub_acc.org_name}",
                               pub_acc=pub_acc,
                               records=test_recs,
                               page=page,
                               num_pages=num_pages,
                               link=f"/account/{pub_uuid}/test_history?pageSize={page_size}{api_key}",
                               stored_months=retained_months("pub_test"))
    return response


# Publisher test result details
@blueprint.route("<pub_uuid>/test_history/record/<rec_id>", methods=["GET"])
@org_user_or_admin_org__gui("pub_uuid")
def test_record(pub_uuid=None, rec_id=None, curr_user=None, cu_org_acc=None):
    """
    Displays test submission history for the given publisher.

    :param pub_uuid: Publisher uuid or abort with a 401.
    :param rec_id: Test record id
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    """
    # If current org-user is Admin, then we want to retrieve Org Account that the Admin user selected (will abort
    # with 404 if not found); otherwise we just use the user's parent Org Account
    pub_acc = _get_org_acc_by_uuid(pub_uuid) if cu_org_acc.is_super and cu_org_acc.uuid != pub_uuid else cu_org_acc

    if pub_acc is None:
        _abort(404, "Publisher account not found.")
    test_rec = PubTestRecord.pull(rec_id)
    if test_rec is None:
        _abort(404, "Test record not found.")

    json_note = json_str_from_json_compressed_base64(test_rec.json_comp, sort_keys=True) or "{}"
    test_rec.json_comp = None   # Don't need to retain large value
    response = render_template('account/pub_test_detail.html',
                               curr_user_acc=curr_user,
                               title="Publisher Test Detail",
                               pub_acc=pub_acc,
                               record=test_rec,
                               json_note=json_note)
    return response


# Publisher test summary
@blueprint.route("test_overview", methods=["GET"])
@admin_org_only__gui
def test_overview(curr_user=None, cu_org_acc=None):
    """
    Displays publisher test summary report.

    Expected URL parameter: `scope` set to "all" or "active"

    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    """
    url_params = request.args
    scope = url_params.get("scope")
    # Default to active
    if scope not in ("all", "active"):
        scope = "active"
    autotest_pubs = AccOrg.get_publishers(auto_test="active" if scope == "active" else "started")
    response = render_template('account/pub_test_overview.html',
                               curr_user_acc=curr_user,
                               title="Publisher Auto-testing Overview",
                               scope=scope,
                               publishers=autotest_pubs)
    return response


# Delete ORG  account
@blueprint.route('/<org_uuid>/delete_org_acc', methods=['DELETE', 'POST'])
@admin_org_only__gui
def delete_org_acc(org_uuid, curr_user=None, cu_org_acc=None):
    """
    :param org_uuid: UUID of organisation to be displayed
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    """
    # CANNOT delete OWN organisation account
    if org_uuid == cu_org_acc.uuid:
        flash('You cannot delete your own organisation account.', 'error')
        return redirect(request.referrer)

    str_timestamp = now_str()

    org_acc = _get_org_acc_by_uuid(org_uuid, for_update=True)

    # Delete UNIX ftp account if Publisher
    if org_acc.is_publisher:
        org_acc.remove_unix_ftp_account()

    # The account record will remain, but with a 'deleted_date' set
    # (it is important that the account is NOT actually removed)
    org_acc.deleted_date = str_timestamp
    org_acc.status = OFF
    # Set contact email to None, otherwise email address cannot be re-used
    org_acc.contact_email = None
    org_acc.update()
    log_msg = f"DELETED {org_acc.role} account '{org_acc.org_name}' ({org_acc.id})."

    num_users = 0
    # Need to mark all related AccUser records as deleted also
    for user_acc in AccUser.pull_user_acs(org_acc.id, for_update=True):
        msg = _delete_user_acc(user_acc, str_timestamp, commit=False)
        log_msg += "\n" + msg
        num_users += 1
    AccUser.commit()

    current_app.logger.info(log_msg)
    flash(f"Deleted Organisation account {org_acc.uuid} ({org_acc.org_name}) and {num_users} related User accounts.")

    return redirect(url_for('.index'))


# Update repository JISC &/or CORE Identifiers
@blueprint.route('/<org_uuid>/update_identifiers', methods=['POST'])
@admin_org_only__gui
def update_identifiers(org_uuid, curr_user=None, cu_org_acc=None):
    """
    :param org_uuid: UUID of organisation to be displayed
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    """
    org_acc = AccOrg.pull(org_uuid, pull_name="uuid", for_update=True)
    form = OrgIdentifiersForm(request.form)
    repo_data = org_acc.repository_data
    repo_data.jisc_id = form.jisc_id.data
    repo_data.core_id = form.core_id.data
    org_acc.update()

    flash('Identifiers have been updated.', "success")
    return redirect(url_for('.disp_org_acc', org_uuid=org_uuid))


@blueprint.route('/bulk_email', defaults={'repo_pub': 'P'}, methods=["GET"])
@blueprint.route('/bulk_email/<path:repo_pub>', methods=["GET"])
@admin_org_only__gui
def bulk_email(repo_pub=None, curr_user=None, cu_org_acc=None):
    """
    Display bulk email GUI.

    :param repo_pub: String - indicates type of organisations to list
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    """
    repo_pub_u = repo_pub[0].upper()  # We want only first upper case character e.g. "P" if "publisher" was entered
    if repo_pub_u in "ARP":
        ac_type = repo_pub_u
    else:
        ac_type = "P"  # Default to publishers
        flash(f"Invalid organisation type '{repo_pub}' entered - defaulting to 'P' (publisher).", "warning")

    title_dict = {"A": "publisher & institution", "P": "publisher", "R": "repository"}
    return render_template(
        'account/bulk_email.html',
        curr_user_acc=curr_user,
        title="Bulk email",
        ac_desc=title_dict[ac_type],
        ac_type=ac_type,
        cc_emails="; ".join(current_app.config.get("CONTACT_CC", []))
    )

@blueprint.route("/bulk_email_ajax", methods=["GET", "POST"])
@admin_org_only_or_401__gui
def bulk_email_ajax():
    """
    Endpoint that handles bulk_email AJAX queries from front end, possible functions:
    get_acc_details, send_email, list_bulk_emails, delete_msgs, highlight_msgs, lowlight_msgs

    JSON data structure varies depending on query being handled.

    IMPORTANT:
        * ac_type is used in conjunction with sending/retrieving Bulk Emails,
                  possible values: "P", "R", "A" or a combination of these, such as "AP";
        * ac_role is used in conjunction with retrieving Org Accounts or User email addresses,
                  possible values: "P", "R", "PR";


    For listing accounts:
    {
    'func': 'list_ac',
    'ac_role': "PR"       // Concatenated string of account types to list - P:Publishers, R:Repos
    }
    ** - May be absent

    For sending Email:
    {
    "func": "send_email",
    "ac_type": "P" or "R" or "A",   # Publishers, Repositories, All - both Pub & Repo
    "to_addr_types": "...",         # String indicates types of email addr selected, containing "C", "T", "A", "S", "R" **
    "cc_addr_types": "...",         # String indicates types of email addr selected, containing "C", "T", "A", "S", "R" **
    "cc_addr": "test_cc@jisc.ac.uk",    # Additional CC email address
    "subject": "Email subject line",
    "body": "Email message body (may contain HTML)",
    "ac_data": [
        {
            "id": 13,                   # Organisation Account ID
            "to": "ftpauto@email.com",  # Ac Contact email
            "cc": null or [] or ["tech-contact@email.com", "another-contact@email.com"]     # CC tech contacts
        },
        ...
    ]
    }
    ** EMAIL ADDR TYPES: C: Org Contact emails, T: Org Tech contact emails, A: Admin users, S: Standard users, R: Readonly users

    For listing emails previously sent:
    {
    'func': 'list_bulk_emails',
    'limit': 10**,         // Max number of records to retrieve
    'ac_type': "PR"        // Type of records to retrieve ("A"=Pub & Repo, "P"=Publishers, "R"=Repositories)
    'rec_status': "D"      // Concatenated string of status values ("N"=Normal/NULL, "H"=Highlighted/pinned, "D"=Deleted)
    }
    ** - May be absent

    For updating status:
    {
    'func': 'update_status',
    'status': 'D' (delete) or 'H' (highlight) or 'N' (NULL - clear),
    'rec_id': 9    // Rec ID to update
    }

    For retrieving User email addresses:
    {
    'func': 'get_user_email_addrs',
    'ac_role': "PR",        // Type of records to retrieve one of ["PR"=Pub & Repo, "P "=Publishers, "R"=Repositories]
    }
    """

    def _list_accounts(json_dict):
        """
        Obtain accounts where the role matches supplied account type
        :param json_dict: Looks like
            {
                'func': 'list_ac',
                'ac_role': "P"  // Concatenated string of account types to list - P:Publishers, R:Repos
             }

        :return: List of account dicts, sorted by Organisation Account-role (type) & Orgname
        """

        def _data_dict_from_ac(acc):
            ac_role = acc.raw_role
            ac_status = acc.status
            ret_dict = {
                "id": acc.id,
                "type": ac_role,
                "orgName": acc.org_name,
                "status": acc.translate_status(ac_status),
                "isOff": ac_status == OFF,
                "isLive": acc.has_live_date(),
                "contact": acc.contact_email or "",
                "techContacts": acc.tech_contact_emails,
            }
            if ac_role == "P":
                ret_dict["pubAutotest"] = acc.publisher_data.in_test
            else:
                repo_data = acc.repository_data
                ret_dict["repoSw"] = repo_data.repository_software or ""
                ret_dict["repoFlavour"] = repo_data.repository_xml_format or ""
            return ret_dict

        return [
            _data_dict_from_ac(ac_obj) for ac_obj in AccOrg.get_all_undeleted_accounts_of_type(json_dict.get("ac_role"), order_by="role ASC, org_name ASC")
        ]

    def _list_bulk_emails(json_dict):
        """
        Retrieve list of bulk emails which have specified status & account type.

        :param json_dict: Example:
            {
            'func': 'list_bulk_emails',
            'limit': 10**,         // Max number of records to retrieve
            'ac_type': "AP"        // Type of records to retrieve ("A"=Pub & Repo, "P"=Publishers, "R"=Repositories)
            'rec_status': "D"      // Concatenated string of status values ("N"=Normal/NULL, "H"=Highlighted/pinned, "D"=Deleted)
            }


        :return: List of record dicts
        """
        ac_type = json_dict.get("ac_type")
        if not ac_type:
            ac_type = "APR"
        return AccBulkEmail.list_email_dicts(json_dict.get("limit"), ac_type, json_dict.get("rec_status"))

    def _send_email(json_dict):
        """
        Code to send emails & update database.
        Bulk emails are sent with a TO address of XXXX.YYYY@YYYY.ac.uk, & only Jisc staff in CC field; most
        recipients are sent as BCC addr.

        json_dict:
        {
            "func": "send_email",
            "ac_type": "P" or "R" or "A",   # Publishers, Repositories, All - both Pub & Repo
            "to_addr_types": "...",         # String indicates types of email addr selected, containing "C", "T", "A", "S", "R" **
            "cc_addr_types": "...",         # String indicates types of email addr selected, containing "C", "T", "A", "S", "R" **
            "cc_addr": "test_cc@jisc.ac.uk",    # Additional CC email address
            "subject": "Email subject line",
            "body": "Email message body (may contain HTML)",
            "ac_data": [
                {
                    "id": 13,                   # Organisation Account ID
                    "to": "ftpauto@email.com",  # Ac Contact email
                    "cc": null or [] or ["tech-contact@email.com", "another-contact@email.com"]     # CC tech contacts
                },
                ...
            ]
        }
        ** EMAIL ADDR TYPES - to_addr_types & cc_addr_types strings may contain following chars:
         "C": Org Contact emails, "T": Org Tech contact emails, "A": Admin users, "S": Standard users, "R": Readonly users

        """
        ac_data_list = json_dict.get("ac_data", []).copy()  # Create a copy
        if not ac_data_list:
            raise Exception("No target accounts selected for emailing")

        _validate_json_dict(json_dict, ("ac_type", "subject", "body"))

        cc_addr_list = _validate_emails(json_dict.get("cc_addr", ""))

        ac_id_list = []
        bcc_to_addr_list = []
        bcc_cc_addr_list = []
        for ac_dict in ac_data_list:
            ac_id_list.append(ac_dict["id"])
            bcc_to_addr_list += ac_dict["to"]
            cc_addrs = ac_dict["cc"]
            if cc_addrs:
                bcc_cc_addr_list += cc_addrs

        # Construct the email message
        email = MailMsg(json_dict.get("subject",""),
                     "mail/bulk_msg.html",
                     msg=json_dict["body"]
                     )
        mail_account = MailAccount()
        # The mail process (AWS mail server) REQUIRES a 'To' address, so we use the sender (XXXX.YYYY@YYYY.ac.uk)
        # which would otherwise (more typically) be added as a BCC address.
        to_list = [mail_account.sender]
        # Remove any duplicates in combined bcc address list
        mail_account.send_mail(to_list, cc=cc_addr_list, bcc=list(set(bcc_to_addr_list + bcc_cc_addr_list)), msg_obj=email)

        ###  Save bulk email record & associated regular note_email records ###

        # Remove unwanted dict items
        for key in ("func", "ac_data"):
            try:
                del json_dict[key]
            except KeyError:
                pass
        # Add new dict items - bulk email addresses are concatenated with semi-colons WITHOUT spaces
        json_dict["bcc_to_addr"] = ";".join(bcc_to_addr_list)
        json_dict["bcc_cc_addr"] = ";".join(bcc_cc_addr_list)
        json_dict["ac_ids"] = ac_id_list

        # Insert acc_bulk_email record
        bulk_rec = AccBulkEmail(json_dict).insert()

        note_email_dict = {
            "bulk_email_id": bulk_rec["id"],
            "type": "B",  # Bulk email
            "status": None
        }
        # Now save related acc_notes_emails records
        for ac_dict in ac_data_list:
            note_email_dict["acc_id"] = ac_dict["id"]
            note_email_dict["to_addr"] = "; ".join(ac_dict["to"])
            note_email_dict["cc_addr"] = "; ".join(ac_dict["cc"] + cc_addr_list)
            AccNotesEmails(note_email_dict).insert()

        return {"msg": "Email sent", "rec": bulk_rec}

    def _update_status(json_dict):
        """
        Update record status for Bulk specified bulk email record & for related acc_notes_emails records.
        json_dict:
            {
            'func': 'update_status',
            'status': 'D' (delete) or 'H' (highlight) or 'N' (NULL - clear),
            'rec_id': 9    // Rec ID to update
            }

        """
        # Update the Bulk Email record
        bulk_count = AccBulkEmail.update_status(json_dict["rec_id"], json_dict["status"])
        # Update associated Notes_emails records
        related_count = AccNotesEmails.update_status_bulk_emails(json_dict["rec_id"], json_dict["status"])
        return {"msg": "Record updated", "bulk_count": bulk_count, "related_count": related_count}

    def _get_user_email_addrs(json_dict):
        """
        Get user email addresses for specified organisation types (roles) - P|R|PR : Publishers|Repos|Both
        :param json_dict:
            {
            'func': 'get_user_email_addrs',
            'ac_role': "PR",        // Type of records to retrieve one of ["PR"=Pub & Repo, "P"=Publishers, "R"=Repositories]
            }
        :return:
        """
        ac_role = json_dict.get('ac_role')
        if ac_role is None:
            raise Exception("Parameter 'ac_role' is required")

        return AccUser.pull_user_emails_roles_org_ids_by_role_n_org_type(ac_role, role_desc=False)


    #### FUNC ####

    func_lookup = {
        "list_ac": _list_accounts,
        "list_bulk_emails": _list_bulk_emails,
        "send_email": _send_email,
        "update_status": _update_status,
        "get_user_email_addrs": _get_user_email_addrs
    }

    data_dict = request.json if request.method == "POST" else request.values
    func_name = data_dict.get("func")
    func = func_lookup.get(func_name)
    if func:
        try:
            result = func(data_dict)    # Execute required function
            return jsonify(result)      # Send response to AJAX request
        except Exception as e:
            err_str = str(e)
            current_app.logger.error(f"In `bulk_email_ajax` - Function '{func_name}' failed with error: {repr(e)}")
    else:
        err_str = f"Function '{func_name}' missing or not recognised"

    # If we get this far then an error has occurred
    json_abort(400, err_str)
    return None


@blueprint.route("/note_email_ajax", methods=["GET", "POST"])
@admin_org_only_or_401__gui
def note_email_ajax():
    """
    Endpoint that handles account notes/emails/to-dos AJAX queries from front end, possible functions:
    * save_note
    * send_email
    * save_todo
    * list_all_types - list notes, emails, todos (as specified by `rec_type` string)
    * update_status
    * list_user_emails - list user email addresses of specified role codes

    JSON data structure (SENT from client via the GET or POST request) varies depending on query being handled.

    For adding notes/emails/todos:
    {
    'func': 'save_note', 'save_todo" or 'send_email',
    'pub_repo_ind': "P" or "R",
    'acc_id': 21,           // Acc ID
    'api_key': "adkfasdfjsahdf"** // Acc API key (only present for emails)
    'to_addr': 'contact.name@somewhere.ac.uk',
    'cc_addr': 'some.person@email.com another.person@elsewhere.co.uk',
    'subject': '...',
    'body': 'xxx',
    'err_ids': [123, 456]**,   // List of error Ids (only present for emails)
    'status': "D" (delete) or "H" (highlight) or ""
    }
    ** - May be absent

    For listing notes/emails/todos:
    {
    'func': 'list_all_types',
    'acc_id': 21,           // Acc ID
    'limit': 10**,          // Max number of records to retrieve
    'rec_type': "NE"        // Concatenated string of type of records to retrieve
    'rec_status': "D"       // Concatenated string of status of records to retrieve
    }
    ** - May be absent

    For listing user email addresses:
    {
    'func': 'list_user_emails',
    'acc_id': 21,           // Org Acc ID
    'role_codes': "NE"**    // Concatenated string of User role codes to retrieve
    }
    ** - May be absent

    For updating status:
    {
    'func': 'update_status',
    'status': 'X'   // Status value - one of "" or "N"(normal/Clear), "H"(Pin/Highlight), "R"(Resolve), "D"(Delete),
    'rec_id': 99,   // List of ID of messages to update
    }

    """
    def _save_note(json_dict):
        """
        Save a Note in the acc_notes_emails table.

        :param json_dict: Dict of record data  to save as JSON.
        :return dict: Success info
        """
        _validate_json_dict(json_dict, ("body", "acc_id"))
        saved_rec = AccNotesEmails(json_dict).insert_note()
        return {"msg": "Note saved", "rec": saved_rec}

    def _save_todo(json_dict):
        """
        Save a ToDo in the acc_notes_emails table.

        :param json_dict: Dict of record data  to save as JSON.
        :return dict: Success info
        """
        _validate_json_dict(json_dict, ["body", "acc_id"])
        saved_rec = AccNotesEmails(json_dict).insert_todo()
        return {"msg": "To-do saved", "rec": saved_rec}

    def _send_email(json_dict):
        """
        Send email to specified addressees & save a record of the Email in the acc_notes_emails table.

        :param json_dict: Dict of record data  to save as JSON.
        :return dict: Success info
        """

        _validate_json_dict(json_dict, ("body", "acc_id"))

        to_addr_list = _validate_emails(json_dict["to_addr"])
        cc_addr_list = _validate_emails(json_dict["cc_addr"])

        # Emails may be entered with space, comma or semicolon separators; but want to store as ';' separated
        json_dict["to_addr"] = "; ".join(to_addr_list)
        if cc_addr_list:
            json_dict["cc_addr"] = "; ".join(cc_addr_list)

        err_ids = json_dict.get("err_ids", [])
        if err_ids:
            # Get class for appropriate datatable that contains the errors
            record_class = SwordDepositRecord if json_dict["pub_repo_ind"] == "R" else PublisherDepositRecord
            err_msg_tuple_list = record_class.get_formatted_errors_for_id_list(err_ids)
            content_href = current_app.config.get("API_URL") + "/{}/content?api_key=" + json_dict["api_key"]
        else:
            record_class = None
            err_msg_tuple_list = []
            content_href = ""

        # Construct the email message
        email = MailMsg(json_dict.get("subject",""),
                     "mail/contact.html",
                     msg=json_dict["body"],
                     error_msg_tuples=err_msg_tuple_list,
                     content_href=content_href
                     )
        MailAccount().send_mail(to_addr_list, cc=cc_addr_list, bcc=current_app.config.get("CONTACT_BCC"), msg_obj=email)

        saved_rec = AccNotesEmails(json_dict).insert_email()
        if err_ids:
            # Now update the error records to show they have been used in an email
            record_class.update_to_indicate_errors_emailed(err_ids)
        return {"msg": "Email sent", "rec": saved_rec}

    def _list_notes_emails_todos(json_dict):
        """
        Retrieve list of notes or emails or todos or all associated with a particular account, which have specified status.

        :param json_dict: dict that must contain "acc_id" element, and may contain "limit" element

        :return: List of record dicts
        """
        return AccNotesEmails.list_notes_emails_todos_dicts(
            json_dict["acc_id"], json_dict.get("limit"), json_dict.get("rec_type"), json_dict.get("rec_status"))

    def _update_status(json_dict):
        """
        Update the status of specified note_email records.

        :param json_dict: dict that must contain "rec_id" & "status" fields
        :return: Dict
        """
        num_changed = AccNotesEmails.update_status(json_dict["rec_id"], json_dict["status"])
        return {"msg": "Record updated", "recs_updated": num_changed}

    func_lookup = {
        "save_note": _save_note,
        "save_todo": _save_todo,
        "send_email": _send_email,
        "list_all_types": _list_notes_emails_todos,
        "update_status": _update_status
    }

    data_dict = request.json if request.method == "POST" else request.values
    func_name = data_dict.get("func")
    func = func_lookup.get(func_name)
    if func:
        try:
            result = func(data_dict)    # Execute required function
            return jsonify(result)      # Send response to AJAX request
        except Exception as e:
            err_str = str(e)
            current_app.logger.error(f"In `note_email_ajax` - Function '{func_name}' failed with error: {repr(e)}")
    else:
        err_str = f"Function '{func_name}' missing or not recognised"

    # If we get this far then an error has occurred
    json_abort(400, err_str)
    return None


# Update Matching Params from JSON directly submitted via AJAX from GUI
# POST: Replace current matching params by new ones; PATCH: Update current matching params by adding new ones.
@blueprint.route('/<org_uuid>/match_params_ajax', methods=['POST', 'PATCH'])
@org_user_or_admin_org_or_401__gui
def set_match_params_ajax(org_uuid, curr_user=None, cu_org_acc=None):
    """
    :param org_uuid: UUID of repo to process
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    """
    # The form submits the following params: file = filename, url = URL to either JSON or a CSV file
    # If current org-user is Admin, then we want to retrieve Org Account that the Admin user selected (will abort
    # with 404 if not found); otherwise we just use the user's parent Org Account
    org_acc = AccOrg.pull(org_uuid, pull_name="uuid") if cu_org_acc.is_super and cu_org_acc.uuid != org_uuid else cu_org_acc

    if not (org_acc and org_acc.is_repository):
        json_abort(403, f"Either the specified account does not exist or is of the wrong type")
    if not request.is_json:
        json_abort(400, "A JSON payload must be submitted.")

    is_ok, msg = post_patch_matching_params(org_acc)
    if not is_ok:
        json_abort(400, msg)

    flash(msg, "success")   # This is flashed because the GUI page is reloaded

    # # Retrieve newly saved matching params
    # matching_params = AccRepoMatchParams.pull(acc.id)
    # # We will return params only of the types submitted
    # return jsonify({"msg": msg, "data": {k: matching_params.matching_config[k] for k in request.json}})

    return jsonify({"msg": msg})


### User Account endpoints ###

def _update_user_acc_n_login(user_acc, remember_me, curr_datetime):
    """
    Log the user in.
    @param user_acc: User A ccount record
    @param remember_me: Boolean - whether user has checked the 'Stay logged in' checkbox
    @param curr_datetime: DateTime object - current timestamp
    @return: Tuple, (Error or None, parent org acc record)
    """
    error = None
    user_acc.last_login_datetime = curr_datetime
    user_acc.login_token = None
    user_acc.update()

    # Retrieve the Router Organisation Account that this user belongs to
    org_acc = AccOrg.pull(user_acc.org_id)
    if org_acc and not org_acc.deleted_date:
        user_acc.acc_org = org_acc
        login_user(user_acc, remember=remember_me)
        flash('Welcome back.', 'success')
    else:
        error = f"Unexpected error: Parent organisation account (ID: {user_acc.org_id}) is missing or deleted"
    return error, org_acc


# Login form
@blueprint.route('/login', methods=['GET', 'POST'])
def login():
    delay = 0
    scroll_to = None
    if request.method == 'POST':
        data_dict = request.values
        error = 'Incorrect username/password.'
        password = data_dict.get('password')
        username = data_dict.get('username')
        if username and password:
            # attempt to pull the user's account
            user_acc = AccUser.pull_by_username(username, for_update=True)
            # if user account found
            if user_acc is not None:
                curr_datetime = now_obj()
                failed_logins = user_acc.failed_login_count
                failed_login_limit = current_app.config["FAILED_LOGIN_LIMIT"]
                can_check_pwd = True
                # If we have failed logins, and the number is an exact multiple of the FAILED_LOGIN_LIMIT
                if failed_logins and failed_logins % failed_login_limit == 0:
                    next_allowed_datetime = user_acc.last_failed_login_datetime + timedelta(seconds=int(failed_logins / failed_login_limit) * current_app.config["FAILED_LOGIN_SLEEP_SECS"])
                    if curr_datetime < next_allowed_datetime:
                        user_acc.cancel_transaction()
                        delay = int((next_allowed_datetime - curr_datetime).total_seconds())
                        # Not enough time has passed since last failed login attempt
                        error = f"Too many failed login attempts - try again in {delay} seconds."
                        can_check_pwd = False

                if can_check_pwd:
                    # If password OK
                    if user_acc.check_password(password):
                        user_acc.failed_login_count = 0
                        remember_me = True if data_dict.get("remember") else False

                        # Direct login allowed
                        if user_acc.direct_login or data_dict.get("emergency") == "bypass":
                            error, org_acc = _update_user_acc_n_login(user_acc, remember_me, curr_datetime)
                            if error is None:
                                ## Returning HERE ##
                                return redirect(url_for('.disp_org_acc', org_uuid=org_acc.uuid))

                        # 2 Step login - need to create & email a access code and set login cookie
                        else:
                            # Create access code etc. for emailing to user
                            login_token = user_acc.create_login_token_n_cookie(remember_me)
                            user_acc.update()
                            access_code = login_token["value"]
                            # NOTE: user_acc.user_email will only be present if username is NOT an email
                            user_email = user_acc.get_email()

                            mail_data = MailMsg(
                                f"Your Publications Router access code: {access_code}.",
                                "mail/login_2_factor.html",
                                # Need to pass _scheme=... because URL was defaulting to "http" for some reason (at least in UAT)
                                access_code=access_code
                            )
                            MailAccount().send_mail([user_email], msg_obj=mail_data)
                            # email_body = quote(f"The%20expected%20login%20link%20has%20not%20arrived%20at%20email%20address:%20{email}.")
                            msg = f"An access code, valid for 5 minutes, has been emailed to you at: <strong>{user_email}</strong>.<br><br>Check your Junk folder if you do not see it in your Inbox. If it does not arrive, please email <a href=\"mailto:YYYY@YYYY.ac.uk?subject=Publications%20Router%20login%20token%20-%20email%20did%20not%20arrive&body=The%20expected%20login%20token%20has%20not%20arrived%20at%20email%20address:%20'{user_email}'.\">XXXX@YYYY.ac.uk</a>, mentioning Publications Router in the email subject line."
                            flash(msg, 'info+html')
                            # Prepare login-link webpage & set cookie which is later used to check that link is used by user
                            # (in the same browser) that requested it - this prevents an unintended recipient of the email
                            # from gaining access to Router.
                            resp = make_response(render_template('account/login_2_factor.html',
                                                                 title='Login',
                                                                 email=user_email,
                                                                 expiry_isoformat=login_token["expiry"],
                                                                 user_uuid=user_acc.uuid,
                                                                 scroll_to="main")
                                                 )
                            resp.set_cookie("login", value=login_token["cookie"],
                                            max_age=None,
                                            expires=datetime.fromisoformat(login_token["expiry"]),
                                            secure=True,
                                            httponly=True)

                            ## Returning HERE ##
                            return resp

                    else: # Password wrong

                        # If we get this far then user record found BUT is either deleted or wrong password
                        failed_logins += 1
                        user_acc.failed_login_count = failed_logins
                        user_acc.last_failed_login_datetime = curr_datetime
                        user_acc.update()
                        # If the number of failed logins is an exact multiple of the  FAILED_LOGIN_LIMIT we impose a delay
                        if failed_logins % failed_login_limit == 0:
                            delay = int(failed_logins / failed_login_limit) * current_app.config["FAILED_LOGIN_SLEEP_SECS"]
                            error = f"Too many failed login attempts - try again in {delay} seconds."

        ## If we get this far, then login failed ##

        flash(error, "error")
        scroll_to = "main"

    # request.method was GET or login request failed
    return render_template('account/login.html', title='Login', delay=delay, scroll_to=scroll_to)


# Respond to access code
@blueprint.route('/token_login', methods=['POST'])
def token_login():
    """
    The link to this endpoint enables a user to login to Router (but only if the browser the link is executed from
    also contains the login cookie).
    """
    # Default error if user_uuid is bad or there was no reset token or the token id was wrong
    error = "Invalid access code - please try again."
    data_dict = request.values
    user_uuid = data_dict.get("user_uuid")
    user_acc = AccUser.pull(user_uuid, pull_name="uuid", for_update=True) if user_uuid else None
    if user_acc:
        login_token = user_acc.valid_login_token()
        # If Token is valid, no error
        if login_token and login_token["value"] == data_dict.get("access_code"):
            # Check whether browser cookie (set when the user login_2_factor.html page is displayed) matches expected
            if login_token["cookie"] != request.cookies.get('login'):
                error = "The access code only works from the same browser that you initiated the login from."
            else:
                # If remember was set, this will be "on" - which casts to True. If it's empty, it will cast to False.
                error, org_acc = _update_user_acc_n_login(user_acc, login_token["remember"], now_obj())
                if error is None:

                    ## SUCCESSFUL LOGIN - RETURNING HERE ##
                    return redirect(url_for('.disp_org_acc', org_uuid=org_acc.uuid))

        ## If got this far then there was a problem

        user_acc.login_token = None   # Reset after any error, so link can be used only once
        user_acc.update()

    flash(error, 'error')
    return redirect(url_for('.login'))


@blueprint.route('/logout')
def logout():
    logout_user()
    flash('You are now logged out', 'success')
    return redirect(url_for('index'))


def _user_data(user_acc):
    return {
        "username": user_acc.username,
        "user_email": user_acc.user_email,
        "surname": user_acc.surname,
        "forename": user_acc.forename,
        "org_role": user_acc.org_role,
        "role_code": user_acc.role_code,
        "user_note": user_acc.note,
        "password": "",
        "password_verify": "",
        "last_success": user_acc.last_login_datetime_str,
        "last_failed": user_acc.last_failed_login_datetime_str,
        "num_failed": user_acc.failed_login_count,
        "direct_login": user_acc.direct_login
    }


def _user_data_disable_fields(is_own_rec, curr_user_acc, data_dict):
    """
    Return list of user data fields to set as disabled
    :param is_own_rec: Boolean - True: User is viewing/editing their OWN record; False: User is viewing another's record
    :param curr_user_acc: Object  - Current user account
    :param data_dict: Dict of data to display
    :return: List of field names TO DISABLE
    """
    # All fields: "username", "user_email", "surname", "forename", "org_role", "role_code", "user_note",
    #             "last_succses", "last_failed", "num_failed", "password", "password_verify"

    # These fields are disabled in the UserDetailsForm  declaration: "last_succses", "last_failed", "num_failed", so
    # don't need to be disabled here
    if curr_user_acc.is_api:
        fields_to_disable = ["username", "user_email", "surname", "forename", "org_role", "role_code", "user_note", "password", "password_verify", "direct_login"]
    else:
        # Only Jisc Admins can allow direct_login for a user, for all other users the field is disabled
        fields_to_disable = []
        if not curr_user_acc.is_jisc_admin:
            # user_email only allowed for jisc-admin
            fields_to_disable.append("user_email")
        if is_own_rec:
            if not curr_user_acc.is_developer:
                # Users (except for Jisc Developers) cannot change their own username, role-code, direct-login
                fields_to_disable += ["username", "role_code", "direct_login"]
        elif not curr_user_acc.is_jisc_admin:
            # Only jisc admins can set direct_login checkbox
            fields_to_disable.append("direct_login")
        elif data_dict["role_code"] == "D" and not curr_user_acc.is_developer:
            # ONLY a Jisc Developer can change the role_code & direct_login of another Jisc Developer (a Jisc-Admin can't)
            fields_to_disable += ["role_code", "direct_login"]

    return fields_to_disable  # List of field names to disable


def _user_role_code_choices(curr_user_acc, org_acc, user_acc=None):
    """

    @param curr_user_acc: Currently logged-in user account
    @param org_acc: Org account associated with user record being viewed/edited
    @param user_acc: User account of user record being viewed/edited
    @return: String of possible role-codes
    """
    # If a normal or read-only user
    if not curr_user_acc.is_admin:
        return curr_user_acc.role_code

    # Jisc Admin user and editing an Admin Org account user
    if curr_user_acc.is_jisc_admin and org_acc.is_super:
        # Read-only/Jisc admin/Developer  OR  Read-only/Jisc admin
        return "RJD" if curr_user_acc.is_developer or (user_acc and user_acc.is_developer) else "RJ"
    return "SRA"    # Standard / Read-only / Admin


def _disp_user_acc(is_own_rec, user_acc, curr_user, user_details_form=None):
    """
    Display User Account web page
    :param is_own_rec: Boolean - True: User is viewing/editing their OWN record; False: User is viewing another's record
    :param user_acc: User Account object (of user being displayed/edited)
    :param curr_user: Currently logged in User Account object
    :param user_details_form: User details form input
    :return: render_template
    """
    if user_details_form is None:
        user_data = _user_data(user_acc)
        user_details_form = UserDetailsForm(data=user_data, acc_id=user_acc.id,
                                            disable_fields=_user_data_disable_fields(is_own_rec, curr_user, user_data))

    user_details_form.set_role_code_choices(_user_role_code_choices(curr_user, user_acc.acc_org, user_acc))

    return render_template('account/user_ac.html',
                           is_own_rec=is_own_rec,
                           curr_user_acc=curr_user,
                           title=f"User Details for {user_acc.username}",
                           user_acc=user_acc,
                           user_details_form=user_details_form
                           )


@blueprint.route('/all_users', methods=['GET'])
@admin_org_only__gui
def list_all_users(curr_user=None, cu_org_acc=None):
    """
    Display organisation user accounts
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    """
    url_params = request.args
    del_on_off = url_params.get("del_on_off", "O")
    org_types = url_params.get("org_types", "RP")
    live_test = url_params.get("live_test", "LT")
    role_codes = url_params.get("role_codes", "SRA")
    title_a = "deleted " if del_on_off == "D" else ""

    return render_template(
        'account/all_user_acs.html',
        curr_user_acc=curr_user,
        user_acs=AccUser.pull_all_user_n_org_accounts(org_types, live_test, role_codes, del_on_off),
        title=f"List {title_a}users of selected types",
        csv_link=url_for(".download_users_csv", **url_params),
        make_sortable_str=make_sortable_str
    )


@blueprint.route('/org_user_count', methods=['GET'])
@admin_org_only__gui
def org_user_count(curr_user=None, cu_org_acc=None):
    """
    Display list of organisations alongside a count of the number of users.
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    """
    url_params = request.args
    on_off = url_params.get("on_off", "OF")
    org_types = url_params.get("org_types", "RP")

    return render_template(
        'account/org_user_count.html',
        curr_user_acc=curr_user,
        org_data_tuples=AccOrg.get_org_user_count(org_types, on_off),
        title=f"List organisation user counts",
        translate_role=AccOrg.role_short_desc,
        sort_col=3,  # initially sort on user count column
        make_sortable_str=make_sortable_str
    )


@blueprint.route('/all_users_csv', methods=['GET'])
@admin_org_only__gui
def download_users_csv(curr_user=None, cu_org_acc=None):
    """
    Display organisation user accounts
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    """
    url_params = request.args
    del_on_off = url_params.get("del_on_off", "O")
    org_types = url_params.get("org_types", "RP")
    live_test = url_params.get("live_test", "LT")
    role_codes = url_params.get("role_codes", "SRA")

    def user_acc_to_data_row(user):
        org = user.acc_org
        live_timestamp = org.live_date or ""
        deleted_timestamp = user.deleted_date or ""
        # For email we use function the email is only populated if username is NOT user's email address.
        return [org.role_short_desc(org.raw_role), "Deleted" if org.deleted_date else "Off" if org.status == 0 else "On", org.org_name, live_timestamp[:10], user.surname, user.forename,
                user.org_role, user.get_email(), user.role_short_desc, deleted_timestamp[:10]]

    data_rows = AccUser.pull_all_user_n_org_accounts(
        org_types=org_types,
        live_test=live_test,
        role_codes=role_codes,
        del_on_off=del_on_off,
        list_func=user_acc_to_data_row
    )
    # Sort by Org-type, org-status, ORG-NAME, SURNAME
    data_rows.sort(key=lambda k: (k[0], k[1], k[2].upper(), k[4].upper()))
    row_count, bytes_io_obj = create_in_memory_csv_file(
        data_iterable=data_rows,
        heading_row=[
            "Org. Type", "Org. Status", "Org. Name", "Live Date", "Surname", "Firstname", "User's Role", "Email", "Router Role", "Deleted date"
        ]
    )
    return send_file(
        bytes_io_obj,
        mimetype='text/csv',
        download_name=f"{'deleted_' if del_on_off == 'D' else ''}users_of_type_{role_codes}_org_type_{org_types}_{live_test}_{del_on_off}.csv",
        as_attachment=True
    )


@blueprint.route('/<org_uuid>/users', methods=['GET'])
@user_admin_or_admin_org__gui
def list_org_users(org_uuid, curr_user=None, cu_org_acc=None):
    """
    Display organisation user accounts
    :param org_uuid: UUID of organisation to be displayed
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    """
    other_record = cu_org_acc.uuid != org_uuid
    # If current org-user is Admin, then we want to retrieve Org Account that the Admin user selected (will abort
    # with 404 if not found); otherwise we just use the user's parent Org Account
    org_acc = _get_org_acc_by_uuid(org_uuid) if other_record else cu_org_acc

    user_ac_list = AccUser.pull_user_acs(org_acc.id)

    return render_template(
        'account/user_acs.html',
        curr_user_acc=curr_user,
        org_acc=org_acc,
        user_acs=user_ac_list,
        title="List Users",
        sort_col=1  # initially sort on column 1
    )


@blueprint.route('/<org_uuid>/add_user', methods=['GET', 'POST'])
@user_admin_or_admin_org__gui
def add_user_acc(org_uuid, curr_user=None, cu_org_acc=None):
    """
    Add new organisation user
    :param org_uuid: UUID of organisation
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    """
    org_acc = _get_org_acc_by_uuid(org_uuid) if cu_org_acc.is_super and cu_org_acc.uuid != org_uuid else cu_org_acc
    user_details_form = UserDetailsForm(request.form)
    user_details_form.set_role_code_choices(_user_role_code_choices(curr_user, org_acc))

    if request.method == 'POST':
        if user_details_form.validate():
            ## Create user account
            user_acc, pwd_reset_url = _create_new_user_acc(org_acc.id, user_details_form.data)
            message = f'{user_acc.role_desc} User account created for: <strong>{user_acc.forename} {user_acc.surname}</strong>.<br><br>Email <a id="f_link" href="{pwd_reset_url}">password reset link</a> <span class="icon-before icon-clipboard clickable-icon super-icon copy" data-action="clipboard" data-function="copy_link" data-target="#f_link"></span> to: <span class="icon-after icon-clipboard-after clickable-icon super-icon copy" data-action="clipboard" data-function="copy_text">{user_acc.get_email()}</span>.'
            flash(message, 'success+html')
            return redirect(url_for('.user_account', org_uuid=org_acc.uuid, user_uuid=user_acc.uuid))

        else:
            flash(_wtforms_validation_error_string(user_details_form, "Details not updated: "), "error")

    return render_template('account/user_ac_add.html',
                           curr_user_acc=curr_user,
                           user_org_acc=org_acc,
                           title=f"Add User for {org_acc.org_name}",
                           user_details_form=user_details_form
                           )


@blueprint.route('/<org_uuid>/user/<user_uuid>', methods=['GET', 'POST'])
@own_user_acc_or_org_admin_or_admin_org__gui
def user_account(org_uuid, user_uuid, curr_user=None, cu_org_acc=None):
    """
    Display A user account

    :param org_uuid: UUID of organisation to which user belongs (this is used by the security decorator)
    :param user_uuid: UUID of User to be displayed
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    """
    # If current user is an Admin of some kind, then we want to retrieve User Account that they selected (will abort
    # with 404 if not found); otherwise we just use the user's Account
    is_own_rec = curr_user.uuid == user_uuid

    if request.method == "GET":
        user_acc = curr_user if is_own_rec else _get_user_n_org_acc_by_uuid(user_uuid)
        user_details_form = None
    else:   # POST
        user_acc = _get_user_acc_by_uuid(user_uuid, for_update=True)
        orig_data = _user_data(user_acc)
        user_details_form = UserDetailsForm(request.form, data=orig_data, acc_id=user_acc.id,
                                            disable_fields=_user_data_disable_fields(is_own_rec, curr_user, orig_data))
        user_details_form.set_role_code_choices()
        if user_details_form.validate():
            user_acc.username = user_details_form.username.data
            user_acc.user_email = user_details_form.user_email.data
            user_acc.surname = user_details_form.surname.data
            user_acc.forename = user_details_form.forename.data
            user_acc.org_role = user_details_form.org_role.data
            user_acc.role_code = user_details_form.role_code.data
            user_acc.note = user_details_form.user_note.data
            user_acc.direct_login = user_details_form.direct_login.data
            if user_details_form.password.data:
                user_acc.set_password(user_details_form.password.data)
                user_acc.reset_token = None
                user_acc.failed_login_count = 0
            user_acc.update()
            flash("User details updated", "success")
            # return redirect(url_for('.user_account', org_uuid=org_uuid, user_uuid=user_uuid))
            return redirect(request.referrer)

        else:
            user_acc.rollback()
            flash(_wtforms_validation_error_string(user_details_form, "Details not updated: "), "error")
            # Need to set the Org-account on the User Account object - from current_user if user is editing their own account,
            # otherwise need to fetch it from database
            user_acc.acc_org = curr_user.acc_org if is_own_rec else AccOrg.pull(user_acc.org_id)

    return _disp_user_acc(is_own_rec, user_acc, curr_user, user_details_form=user_details_form)


@blueprint.route('/<org_uuid>/user/<user_uuid>/delete', methods=['POST'])
@user_admin_or_admin_org__gui
def delete_user_acc(org_uuid, user_uuid, curr_user=None, cu_org_acc=None):
    """
    Delete a user account
    :param org_uuid: UUID of organisation to which user belongs (this is used by the security decorator)
    :param user_uuid: Organisation UUID - passed by blueprint
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION

    :return:
    """
    # If current user is an Admin of some kind, then we want to retrieve User Account that they selected (will abort
    # with 404 if not found); otherwise we just use the user's Account
    user_acc = _get_user_acc_by_uuid(user_uuid, for_update=True)

    msg = _delete_user_acc(user_acc, now_str())
    current_app.logger.info(msg + f" [Parent Org ID: {user_acc.org_id}].")
    flash(f"Deleted account for: <strong>{user_acc.forename} {user_acc.surname}</strong> (ID: {user_acc.uuid})", "success+html")

    # User just deleted their own account
    if user_uuid == curr_user.uuid:
        logout_user()

    return redirect(url_for('.list_org_users', org_uuid=org_uuid))


# Enter new password form
@blueprint.route('/user/<user_uuid>/reset_password/<token_val>', methods=['GET', 'POST'])
def reset_password(user_uuid, token_val):
    """
    When given a link to this endpoint, allows a user to reset their password.

    GET: Display a password reset form to create and verify the user's new password, as long as the token is valid.
    POST: Validate that they have typed in their password correctly, update their password and redirect them to the
        login page.

    :param user_uuid: User Account id that will have a password reset
    :param token_val: Value of the account's password reset token
    """
    user_acc = AccUser.pull(user_uuid, pull_name="uuid", for_update=request.method == "POST")
    # Default error if there was no reset token or the token id was wrong
    flash_message = "There was no valid reset token."
    if user_acc:
        reset_token = user_acc.valid_reset_token()
        if reset_token and reset_token["value"] == token_val:
            # Token is valid, no error
            flash_message = None

    if flash_message:
        flash(flash_message, 'error')
        return redirect(url_for('.reset_token'))

    pwd_form = PasswordUserForm(request.form)

    if request.method == "POST":
        if pwd_form.password.data:
            if pwd_form.validate():
                user_acc.set_password(pwd_form.password.data)
                # Delete the reset token
                user_acc.reset_token = None
                user_acc.failed_login_count = 0
                user_acc.update()
                flash('Your password has been successfully updated. Please log back in.', 'success')
                return redirect(url_for('.login'))
        else:
            flash('A password must be entered', 'error')
        user_acc.rollback()

    # If we get this far then either a GET request or a failed POST
    url = url_for(".reset_password", user_uuid=user_uuid, token_val=token_val)
    return render_template(
        'account/reset_password.html',
        title='Reset Password',
        reset_url=url,
        form=pwd_form,
        account_username=user_acc.username
    )


# Generate a reset token
@blueprint.route('/<org_uuid>/user/<user_uuid>/reset_token', methods=['POST'])
@user_admin_or_admin_org__gui
def admin_reset_token(org_uuid, user_uuid, curr_user=None, cu_org_acc=None):
    """
    Used to allow admins to create reset tokens for any User account (NOT Org account).

    POST: Creates a password reset token for the given user, then redisplays the account page at the password reset box.

    :param org_uuid: UUID of organisation to which user belongs (this is used by the security decorator)
    :param user_uuid: User Account id to create a reset token for
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    """
    user_acc = _get_user_acc_by_uuid(user_uuid, for_update=True)
    user_acc.create_reset_token()
    user_acc.update()
    return redirect(f"{url_for('.user_account', org_uuid=org_uuid, user_uuid=user_uuid)}#password_reset_box")


# Password reset request form
@blueprint.route('/reset_token', methods=['GET', 'POST'])
def reset_token():
    """
    ** /account/reset_token/ **

    Used when a user has forgotten their password.

    GET: Displays a form for entering their contact email/username and requesting a password reset.
    POST: Handles the password reset request, checking if there is a matching account to the email or username given
        by a GET request, and if OK, generates a password reset token.
    """
    if request.method == 'GET':
            return render_template('account/reset_token.html', title='Request Password Reset')
    else:
        # UUU - Review
        username = request.values.get("username")
        if username:
            user_acc = AccUser.pull_by_username(username, for_update=True)
            if user_acc:
                token = user_acc.create_reset_token()
                user_acc.update()

                # NOTE: user_acc.user_email will only be present if username is NOT an email
                user_email = user_acc.user_email or username
                # Email body is assigned to href attribute, so quote is used to replace spaces by %20 entities
                email_body = quote(
                    "I would like to reset my Publications Router account password. My contact email address for receiving a password reset link is: [ENTER EMAIL HERE]. \n\n [PLEASE PROVIDE YOUR DETAILS]"
                )
                email_text = f'please email <a href="mailto:YYYY@YYYY.ac.uk?subject=Publications%20Router%20password%20reset%20request%20-%20{{}}&body={email_body}">XXXX@YYYY.ac.uk</a>, mentioning Publications Router in the email subject line'

                # If contact email looks like an email address
                if email_validator_regex.match(user_email):
                    mail_data = MailMsg(
                        "Your Publications Router password reset request",
                        "mail/reset_password.html",
                        # Need to pass _scheme=... because was defaulting to "http" for some reason (at least in UAT)
                        reset_url=url_for('.reset_password', user_uuid=user_acc.uuid, token_val=token["value"],
                                          _external=True, _scheme=current_app.config["PREFERRED_URL_SCHEME"])
                    )
                    MailAccount().send_mail([user_email], msg_obj=mail_data)

                    text = 'A password reset link has been emailed to you at "{}".<br><br>If it does not arrive, {}.'.format(
                        user_email,
                        # The text is assigned to href attribute, so quote is used to replace spaces by %20 entities
                        email_text.format(quote("email didn't arrive"))
                    )

                    flash(text, 'success+html')
                else:
                    # User Account didn't have a valid contact email

                    text = 'Account for "{}" has no email address.<br><br>To reset your password {} and providing an email address to send the password reset link to.'.format(
                        username,
                        # The text is assigned to href attribute, so quote is used to replace spaces by %20 entities
                        email_text.format(quote("no contact email address"))
                    )
                    flash(text, 'error+html')
            else:
                flash(f'No Publications Router user account exists for username "{username}"',
                      'error+html')

        return render_template('account/reset_token.html', title='Request Password Reset')


