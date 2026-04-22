"""
Module which handles all the routing mechanics to convert UnroutedNotifications into either
RoutedNotifications or FailedNotifications
"""
import re
from dateutil.relativedelta import relativedelta
# from logging import INFO, WARNING, ERROR, CRITICAL
from octopus.modules.logger.logger import ERROR_X
from octopus.lib import dates
from octopus.modules.mysql.dao import DAOException
from router.shared.models.note import RoutedNotification
from router.shared.models.account import AccOrg
from router.shared.models.doi_register import duplicate_doi_check
from router.jper.unpacked import UnpackUtil
from router.jper import packages
from router.jper.models.publisher import PublisherDepositRecord
from router.jper.models.repository import MatchProvenance
from flask import current_app

# Default licence/embargo calculation indicators
NO_DEFAULT_APPLIED = 0
EMBARGO_CALCULATED = 1
DEFAULT_LICENCE_END_DATE_FROM_PUB_DATE = 2
DEFAULT_LICENCE_NO_END_DATE = 3
DEFAULT_LICENCE_NO_DATE = 4
EMBARGO_NO_LICENCE = 5
EMBARGO_NO_DATE_NO_LICENCE = 6
EMBARGO_CALCULATED_NO_LICENCE = 7

IGNORE = 0
MINOR = 1
MAJOR = 2

applied_default_descriptions = {
    EMBARGO_CALCULATED: (IGNORE, "Embargo end date set from licence start date"),
    DEFAULT_LICENCE_END_DATE_FROM_PUB_DATE: (MINOR, "No licence in metadata, but publisher default licence was applied with start date"),
    DEFAULT_LICENCE_NO_END_DATE: (MINOR, "No licence in metadata, but 'under embargo (end date unknown)' licence text applied"),
    DEFAULT_LICENCE_NO_DATE: (MINOR, "No licence in metadata, but publisher default licence was applied"),
    EMBARGO_CALCULATED_NO_LICENCE: (MAJOR, "No licence in metadata, although embargo duration is provided (embargo end date derived from publication date)"),
    EMBARGO_NO_LICENCE: (MAJOR, "No licence in metadata, although an embargo is provided"),
    EMBARGO_NO_DATE_NO_LICENCE: (MAJOR, "No licence in metadata, although an embargo duration is provided")
}

def get_routing_default_description(default_applied):
    """
    Get description of default that may have been applied

    :param default_applied: Int - indicator returned by `apply_licence_defaults()` function

    :return: Tuple: (Int - Level-indicator MINOR:1  or MAJOR:2, String - Description) or (None, None)
    """
    return applied_default_descriptions.get(default_applied, (None, None))

def add_embargo_months(start_date, months):
    """
    Functioning used in calculating an embargo date given a publication date and embargo period in months.

    Add a number of months to a YYYY-MM-DD date or a YYYY-MM date and return date in YYYY-MM-DD format.
    If date is provided in YYYY-MM format rather than YYYY-MM-DD format, we assume the resulting date
    is set to the last day of that respective month. For example, 2017-01 + 1 month ->
    2017-02-28. Or 2017-01 + 10 -> 2017-11-30.
    If the resulting date would have a DD value that exceeds the maximum days for the month
    then the DD value is set to the last permissable day of the month.
    For example 2017-01-30 plus 1 month --> last day of Feb 2017-02-28.

    :param start_date: String - Date in form 'YYYY-MM-DD' or 'YYYY-MM'
    :param months: - number of months to add to the date.
    :return string date in format 'YYYY-MM-DD' if successful or None if failed
    """
    try:
        # if date of form 'YYYY' return empty string, cannot calculate embargo with this data
        if len(start_date) < 5:
            return None
        # convert our string to a datetime object and add the number of months
        new_date = dates.ymd_to_datetime(start_date) + relativedelta(months=int(months))
        # if not a full date then ensure we set to be the last day of the month
        if len(start_date) < 10:
            new_date += relativedelta(day=31)
        return new_date.strftime("%Y-%m-%d")
    # ymd_to_datetime may throw a ValueError if start_date is not a YMD date
    except ValueError:
        return None


def apply_licence_defaults(routed_embargo, routed_licenses, notification, publisher_data):
    """
    Apply default license and embargo to the notification if it has no licensing information. If there is licensing
    information, but no embargo information- attempt to derive an embargo from the licenses present.

    :param routed_embargo: Dict - embargo information (from notification.embargo)
    :param routed_licenses: List of licenses (from notification.licenses)
    :param notification: the notification to have defaults applied to
    :param publisher_data: Publisher data object (from publisher Account record)
    :return: Int - 0 - no defaults applied; Other values - see `Default licence/embargo calculation indicators` above
    """
    default_applied = NO_DEFAULT_APPLIED
    # If we have licences but no embargo, try to set the embargo
    if routed_licenses:
        if not routed_embargo:
            embargo_end = _derive_embargo_from_licenses(routed_licenses)
            if embargo_end:
                notification.set_embargo(end=embargo_end)
                default_applied = EMBARGO_CALCULATED
    # Else no licences, but an embargo
    elif routed_embargo:
        if notification.provider_route == "api":    # API submission
            embargo_end = routed_embargo.get("end")
            if embargo_end:
                # Future end date, but no licence
                if embargo_end > dates.now_str("%Y-%m-%d"):
                    notification.set_license(
                        title="This article is under embargo, with an unspecified post-embargo licence – please check publisher information"
                    )
                    default_applied = EMBARGO_NO_LICENCE
            else:
                # if duration is absent or empty string, 0 will be used
                embargo_length = int(routed_embargo.get("duration") or 0)
                if embargo_length > 0:
                    routed_pub_date = notification.get_publication_date_string()
                    if routed_pub_date:
                        embargo_end = add_embargo_months(routed_pub_date, embargo_length)
                        notification.set_embargo(start=routed_pub_date, end=embargo_end, duration=embargo_length)
                        notification.set_license(
                            title="This article is under embargo, with an unspecified post-embargo licence – please check publisher information"
                        )
                        default_applied = EMBARGO_CALCULATED_NO_LICENCE
                    else:
                        notification.set_license(
                            title="This article is under embargo with an end date yet to be finalised"
                        )
                        default_applied = EMBARGO_NO_DATE_NO_LICENCE
    else:   # Else no licences and no embargo
        if publisher_data:
            default_license = publisher_data.license
            default_embargo_length = publisher_data.embargo
            if default_license and default_embargo_length is not None:
                routed_pub_date = notification.get_publication_date_string()
                default_embargo_length = int(default_embargo_length)
                if routed_pub_date:
                    embargo_end = add_embargo_months(routed_pub_date, default_embargo_length)
                    if default_embargo_length > 0:
                        notification.set_embargo(start=routed_pub_date, end=embargo_end, duration=default_embargo_length)
                    notification.set_license(
                        url=default_license.get("url"),
                        type=default_license.get("type"),
                        title=default_license.get("title"),
                        version=default_license.get("version"),
                        start=embargo_end
                    )
                    default_applied = DEFAULT_LICENCE_END_DATE_FROM_PUB_DATE
                elif default_embargo_length > 0:
                    # we can't calculate an embargo ourselves (as we have no publication date, so set a default)
                    notification.set_embargo(end="9999-12-31", duration=default_embargo_length)
                    notification.set_license(
                        title="This article is under embargo with an end date yet to be finalised"
                    )
                    default_applied = DEFAULT_LICENCE_NO_END_DATE
                else:
                    # Default licence is zero - set licence without start date
                    notification.set_license(
                        url=default_license.get("url"),
                        type=default_license.get("type"),
                        title=default_license.get("title"),
                        version=default_license.get("version")
                    )
                    default_applied = DEFAULT_LICENCE_NO_DATE
    return default_applied


def _derive_embargo_from_licenses(licenses):
    """
    Derive an embargo from a list of licenses if we can. If any of our licenses are considered open licenses
    we will take its start date (if they have one) and use this as our embargo end date. Note that if we find
    an open license without a start date, then we'll return with None anyways (as the notification is already open!)

    :param licenses: licenses to derive the embargo from

    :return: an embargo end date, or None if an embargo can't be derived from the licenses
    """
    embargo_end = None
    for license in licenses:
        # If license is considered open
        if RoutedNotification.is_open_license(license):
            # set our embargo end date to this license's start date (not this could be None, that's fine)
            embargo_end = license.get("start")
            break
    return embargo_end


def _create_routed(unrouted, repo_ids, reqd_pkg_types, metrics=None, duplicate_diffs=None):
    """
    Create a routed notification from unrouted
    :param unrouted: Object - UnroutedNotification or HarvestedNotification
    :param repo_ids: List - repository IDs to which notification has been routed
    :param reqd_pkg_types: List - Packaging types required by the various repositories
    :param metrics: Dict - Information about current notification
    :param duplicate_diffs: List of Dict - Information about difference between this notification and original and
                            possibly previous best version (for 2nd duplicate onwards)
    :return: Tuple - routed-notification, publisher-org-acc-object (may be None)
    """
    pub_acc = None
    if unrouted.packaging_format:
        # Need to add link to original content - this is done here and not in the API create_unrouted_note to save a
        # database update
        unrouted.add_link("package",
                          "application/zip",
                          "router",
                          cloc="",   # The primary link to original content has no filename (empty content location)
                          packaging=unrouted.packaging_format)

    routed = unrouted.make_routed()

    routed.set_category_if_empty()   # Set article category (aka resource type) if NOT already set

    # repackage the content that came with the unrouted notification (if necessary) into formats acceptable to
    # the repositories for which there was a match. (This uses the packaging-preferences set for repo via GUI).
    pack_links = repackage(unrouted, reqd_pkg_types)
    for pl in pack_links:
        routed.add_link_dict(pl)
    routed.repositories = repo_ids
    routed.analysis_date = dates.now_str()

    level_of_default_applied = None     # Indicates importance of any default that is applied
    # If NOT a harvested notification (i.e. it came from a publisher), then apply defaults if needed
    if routed.provider_harv_id is None:
        # Set local variables to avoid repeated (costly) calls to getters
        routed_embargo = routed.embargo
        routed_licenses = routed.licenses
        routed_peer_reviewed = routed.peer_reviewed

        # If both routed-embargo and routed-licences are None/empty or if routed_peer_reviewed then we need the
        # Publisher Account record to retrieve Publisher default values from
        if (routed_embargo is None and not routed_licenses) or routed_peer_reviewed is None:
            # Retrieve publisher record
            pub_acc = AccOrg.pull(routed.provider_id)
            publisher_data = pub_acc.publisher_data
            # If peer-reviewed status not set in notification, and exists in publisher record then set in notification
            if routed_peer_reviewed is None and publisher_data.peer_reviewed:
                routed.peer_reviewed = True
        else:
            publisher_data = None

        # If either embargo or licenses are missing, then derive values or set defaults
        if routed_embargo is None or not routed_licenses:
            level_of_default_applied, log_msg = get_routing_default_description(
                apply_licence_defaults(routed_embargo, routed_licenses, routed, publisher_data))

    if metrics:
        routed.metrics = metrics
    if duplicate_diffs:
        routed.dup_diffs = duplicate_diffs

    routed.save_newly_routed()

    if level_of_default_applied:
        msg = f"{log_msg} for notification Id: {routed.id}, {{}}publisher Id: {routed.provider_id} ({routed.provider_agent})."
        if level_of_default_applied == MAJOR:
            current_app.logger.warning(msg.format("YOU SHOULD INFORM the "),
                                       extra={"mail_it": True, "subject": "Default applied"})
        else:
            current_app.logger.info(msg.format(""))

    return routed, pub_acc


def route(unrouted, test_publishers=None, test_harvesters=None, active_repo_tuples_list=None):
    """
    Attempt to route an UnroutedNotification or HarvestedNotification to the appropriate repositories.

    The function will extract relevant matching data from the given notification, comparing this data in
    the matching process with the repository configurations of all "turned on" repositories.

    If there is a match to one or more of the criteria, MatchProvenance objects will be created for
    each matching repository, and persisted for later inspection.

    If one or more repositories are matched, a RoutedNotification will be created, then persisted.

    :param unrouted: an UnroutedNotification or HarvestedNotification object
    :param test_publishers: List of test publisher account IDs
    :param test_harvesters: List of test harvester webservice account IDs
    :param active_repo_tuples_list: list of tuples [(repo-id, is-live-boolean, repository-data-object, match-params-dict),]
    :return: True if the notification was routed to a repository, False if there were no matches
    """
    debugging = current_app.config.get("LOG_DEBUG")

    # Set provider_id to either the Harvester webservice ID (harv_id) or Publisher ID (provider_id)
    # Determine if the provider is live or not

    is_publisher_notification = unrouted.provider_harv_id is None
    # If notification is from a publisher source (FTP or API)
    if is_publisher_notification:
        provider_id = unrouted.provider_id
        provider_live = provider_id not in test_publishers
        prefixed_provider_id = f"p{provider_id}"
    else:  # Notification is harvested
        provider_id = unrouted.provider_harv_id
        provider_live = provider_id not in test_harvesters
        prefixed_provider_id = f"h{provider_id}"

    # Init various variables to None
    doi_rec = metrics = duplicate_level = duplicate_diffs = note_from_pub = prev_recipient_ids = None
    match_ac_ids = []
    match_provenance_obj_list = []  # Stores list of match_provenance objects for later insertion (once routed.id is known)
    reqd_pkg_types = set()  # Set of package types required across all matched repos
    one_or_more_repos_live = False  # Flag to indicate if one of the matched repos is Live
    routing_msg = "Routing - {} {} ID: {}".format(
        'Live' if provider_live else 'Test', unrouted.__class__.__name__, unrouted.id)
    # extract the match data from the notification
    match_data = unrouted.match_data()
    if match_data.is_sufficient():
        if debugging:
            current_app.logger.debug(f"{routing_msg} *** using MATCHING data: {match_data.json()}")
        try:
            # If provider is live, then we will attempt to match against ALL active repositories, but if provider is
            # not live (test) then attempt to match against only test (not-live) repositories
            # The effect of this is that notifications from Test (non-Live) sources can never be matched to Live repositories
            # (Because the number of accounts is modest, we don't need to use a scroller function here)
            # Iterate through the configs of the repositories, saving match provenance and collecting
            # a list of matched repositories
            for repo_id, repo_is_live, repository_data, match_params_dict in active_repo_tuples_list:
                # If provider is NOT live then we only want to process Non-Live (i.e. Test) Repositories
                if not provider_live and repo_is_live:
                    continue

                # If originator (publisher or harvester web-service) of Notification is in the repository's exclusion list
                if prefixed_provider_id in repository_data.excluded_provider_ids:
                    continue  # Skip checking and continue with next repository

                # check whether notification matches repository config
                provenance = match(match_data, repo_id, repository_data, match_params_dict)
                if provenance:
                    # Not yet checked if this notification's DOI was previously seen
                    if duplicate_level is None:
                        # Note that in rare cases, if the notification has no DOI, then doi_rec will be None
                        # and duplicate_level will be 0
                        doi_rec, metrics, note_from_pub, duplicate_level, duplicate_diffs = duplicate_doi_check(unrouted)
                        if duplicate_level:
                            prev_recipient_ids = doi_rec.repos

                    # Notification's DOI has been seen before AND previously routed to this repository and NOT first publisher notification and duplicates NOT wanted
                    if duplicate_level and repo_id in prev_recipient_ids and not (note_from_pub and doi_rec.pub_count == 1) and not repository_data.dups_wanted(note_from_pub, duplicate_level):
                        continue

                    ## If we get this far, then this notification will be routed to this repository ##

                     # Add the repository to the list of successfully matched repositories
                    match_ac_ids.append(repo_id)
                    # Store provenance for later insertion when the routed notification ID is known
                    match_provenance_obj_list.append(provenance)

                    # Set flag if matched repo is live
                    if repo_is_live:
                        one_or_more_repos_live = True

                    # Add repository's packaging type to set of types
                    reqd_pkg_types.add(repository_data.packaging)

                    if debugging:
                        current_app.logger.debug("{} MATCHED {} repo:{}".format(
                            routing_msg, 'Live' if repo_is_live else 'Test', repo_id))

        except Exception as e:
            current_app.logger.error(f"{routing_msg} failed with error '{repr(e)}'")
            raise e
    else:
        if debugging:
            current_app.logger.debug(f"{routing_msg} *** has no effective MATCHING data")

    if debugging:
        current_app.logger.debug(f"{routing_msg} matched to {len(match_ac_ids)} repositories")

    # if there are matches then the routing is successful, so a "routed" notification is created & its any associated
    # file content is prepared (repackaged) for download
    if match_ac_ids:
        # Create routed notification from unrouted.
        # NB. For Harvested notifications, a new routed record (with different ID) will be created
        routed, pub_acc = _create_routed(unrouted, match_ac_ids, reqd_pkg_types, metrics, duplicate_diffs)
        routed_id = routed.id

        if debugging:
            current_app.logger.debug(f"{routing_msg} SUCCESSFULLY ROUTED; RoutedNotification ID: {routed_id}.")

        if doi_rec:
            doi_category = doi_rec.category
            # If doi_rec.category not yet set, or is different from current publisher's notification category
            if not doi_category or (doi_category != routed.category and note_from_pub):
                doi_rec.category = routed.category

            # Add match IDs to the record
            doi_rec.add_repo_ids(match_ac_ids)
            if one_or_more_repos_live:
                doi_rec.routed_live = True
            # Only save doi_rec if data has changed (if there were no new match_ac_ids, then data may not have changed)
            doi_rec.save_if_changed()

        exc_raised = None
        for match_prov in match_provenance_obj_list:
            try:
                # Set notification ID to (newly) created routed notification
                match_prov.note_id = routed_id
                # save the provenance data to DB
                match_prov.insert()
            except Exception as e:
                exc_raised = e
                current_app.logger.critical(
                    f"Failed to insert Match Provenance record for notification Id: {routed_id}; but continuing with processing. {str(e)}")
                if isinstance(e, DAOException) and e.abend:
                    break

        if is_publisher_notification:
            # Add to the deposit record whether it matched to any repositories, and whether it
            # matched to any live (as opposed to test) repositories.
            pub_deposit_record = PublisherDepositRecord.get_by_notification_id(routed_id, for_update=True)
            if pub_deposit_record:
                # If we have a record, set it to be matched.
                pub_deposit_record.matched = True
                if one_or_more_repos_live:
                    # Indicate that the record matched at least one live repo account
                    pub_deposit_record.matched_live = True
                try:
                    pub_deposit_record.update()
                except Exception as e:
                    exc_raised = e
                    current_app.logger.critical(
                        f"Failed to update Publisher Deposit record for notification Id: {routed_id}. {str(e)}")

                # Raise error to publisher here if zip file was missing a PDF
                # (This used to be done elsewhere (upon file ingest), but doing it after successful routing means that
                # publishers are only alerted to potentially consequential problems)
                file_name = pub_deposit_record.name
                if file_name and not routed.has_pdf:
                    # Publisher account may or may not have been retrieved in _create_routed above
                    if pub_acc is None:
                        pub_acc = AccOrg.pull(routed.provider_id)
                    msg_a = f"No PDF file was found in the submitted zip file: '{file_name}' (DOI: {routed.article_doi})."
                    msg_b = " If there should have been a PDF included then please resubmit, otherwise no further action is needed as the submission has been processed."
                    pub_acc.send_email(f"Publications Router submission issue - file '{file_name}'",
                                       msg_a + msg_b,
                                       to=pub_acc.TECHS,
                                       email_template="mail/pub_issue.html",
                                       save_acc_email_rec=True
                                       )
                    current_app.logger.log(ERROR_X, f"route: {msg_a} from '{pub_acc.org_name}' (Id: {pub_acc.id})")
            else:
                current_app.logger.critical(
                    f"Expected Publisher Deposit record for notification Id: {routed_id} not found.")
        if exc_raised:
            raise exc_raised

        return True
    else:
        if debugging:
            current_app.logger.debug(f"{routing_msg} was not routed")
        return False
    # Note that we don't delete the unrouted notification here - that's for the caller to decide


def get_repo_ids_n_pkg_types_matching_org_name(get_live, org_match_str):
    """
    Find test repositories with Organisation names starting with particular string
    :param get_live: Boolean - True: get Live repos; False: get Test repos
    :param org_match_str: Organisation name which may contain wild-cards ('*' or '%')
    :return: Tuple: (list-of-repo-ids, set-of-package-types)
    """
    repo_ids = []
    reqd_pkg_types = set()  # Set of package types required across all matched repos
    # Get test repositories
    for account in AccOrg.get_active_repos_with_org_name(get_live, org_match_str):
        repo_ids.append(account.id)
        reqd_pkg_types.add(account.repository_data.packaging)

    return repo_ids, reqd_pkg_types


def route_to_specified_test_repos(unrouted, repo_ids, reqd_pkg_types, reason="Unspecified"):
    """
    Route a (test) notification to specific repositories.
    This code DOES NOT DO any of the following:
        - matching (using matching params)
        - updating publisher deposit history

    :param unrouted: Unrouted notification
    :param repo_ids: List of repository_ids
    :param reqd_pkg_types: Set of required packaging types
    :param reason: String - Reason for routing to specific repositories
    :return: routed notification or None
    """
    routed = None
    if repo_ids:
        routed, _ = _create_routed(unrouted, repo_ids, reqd_pkg_types)

        # Create Match provenance records for each repository that Notification has been routed to
        text = "** {}{}Routing to specific repositories **".format(reason, " - " if reason else "")
        for repo_acc_id in repo_ids:
            # Create dummy Match Provenance records
            prov = MatchProvenance({
                "note_id": routed.id,
                "repo_id": repo_acc_id,
                "provenance": [{
                    "source_field": "name_variants",
                    "explanation": reason,
                    "notification_field": "n/a",
                    "term": text,
                    "matched": "…"
                }],
            })
            prov.insert()

    return routed


def domain_email(domain, email):
    """
    Checks whether the email string ends with domain.

    :param domain: domain string (already normalised)
    :param email: any email address
    :return: String if match, False if not
    """
    if re.search(r"\b" + domain + "$", email):
        return f"Email address '{email}' has domain '{domain}'"
    return False


def affiliation_domain(domain, affiliation):
    """
    Checks whether the domain exists within the affiliation string

    :param domain: domain string (already normalised)
    :param affiliation: string containing affiliation info
    :return: String if match, False if not
    """
    # Because domain has no spaces, we can simply convert affiliation to lower-case
    if re.search(r"\b" + domain + r"\b", affiliation.lower()):
        return f"Found email address with domain '{domain}' in '{affiliation}'"
    return False


def postcode_match(param_pc, meta_pc):
    """
    Normalise postcodes: strip whitespace and lowercase, then exact match required

    :param param_pc: matching param postcode
    :param meta_pc: metadata postcode
    :return: True if match, False if not
    """
    # Post-codes never have leading/trailing spaces due to the way they are extracted
    # So, for matching we remove ALL space and convert to lowercase
    npc1 = param_pc.replace(" ", "").lower()
    npc2 = meta_pc.replace(" ", "").lower()

    if npc1 == npc2:
        return f"Postcode from article '{meta_pc}' matched '{param_pc}'"
    return False


def exact_substring(match_param, meta_value):
    """
    Normalised match_param must be an exact substring of normalised meta_value. Important, match_param is adjusted to start on a
    word boundary.  (Normalisation has already taken place - when matching params are loaded and match-data extracted
    from notification).
    :param match_param: String - Original string that r_match_param is derived from
    :param meta_value: String - To be searched for match_param
    :return: True if match, False if not
    """
    if re.search(r"\b" + match_param, meta_value):
        return f"'{match_param}' appears in '{meta_value}'"
    return False


def exact(match_param, meta_value):
    """
    Match parameter must be identical to meta_value (Assume both are already normalised)

    :param match_param: String - matching parameter
    :param meta_value: String - metadata value
    :return: True if match, False if not
    """
    if match_param == meta_value:
        return f"'{match_param}' exactly matches '{meta_value}'"
    return False


def match(routing_metadata, repo_id, repository_data, matching_params):
    """
    Match the incoming notification data, to the repository config and determine
    if there is a match. Returns the provenance data of the first matching parameter which
    results in a match.

    NB. The returned MatchProvenance object will be MISSING the Notification ID at this stage.

    :param routing_metadata:   note_models.RoutingMetadata
    :param repo_id: Integer - Repository account ID
    :param repository_data: Object - Repository data object
    :param matching_params: Dict - Repository Matching params dict

    :return:  a MatchProvenance object if successfully matched, containing the match information. Otherwise None
    """
    # The order in which to match the various repository configuration fields, determined by cost of performing match &
    # frequency of particular routing_metadata type. E.g. If present in routing_metadata & matching_params, we expect
    # relatively few org_ids, postcodes & the matching functions are relatively "cheap"
    # Tuple: (match_param_type, corresponding-matching_param_key, [(metadata_attrib, match_func), (...)])
    prioritised_matching_param_control = [
        # Org-IDs should exactly match
        ("org_ids", "org_ids", [("org_ids", exact)]),
        # for postcodes, look for exact postcode match
        ("postcodes", "postcodes", [("postcodes", postcode_match)]),
        # for domains, look in extracted emails & affiliations
        ("domains", "domains", [("emails", domain_email), ("affiliations", affiliation_domain)]),
        # for name variants, look for exact match in affiliations
        ("name_variants", "name_variants", [("affiliations", exact_substring)]),
        # for grants, look for exact match with extracted grants
        ("grants", "grants", [("grants", exact)]),
        # ORCIDS should exactly match
        ("author_orcids", "orcids", [("orcids", exact)]),
        # Emails should exactly match
        ("author_emails", "emails", [("emails", exact)])
    ]

    # Only process notification if it is NOT too old for the current account
    if not routing_metadata.is_too_old(repository_data.max_pub_age):
        ## Check if metadata contains one of the repository's matching parameters; return at first match.

        # for each repository matching param property in our ordered list
        for match_param_type, match_param_key, comparison_list in prioritised_matching_param_control:
            match_params_list = matching_params.get(match_param_key)
            # If no matching parameters of this type, then skip to next
            if match_params_list is None:
                continue

            # for each matching property and corresponding comparison function, associated with our matching type
            for metadata_attrib, match_func in comparison_list:
                # Loop thru routing metadata array corresponding to a metadata_attrib (e.g. emails etc)
                for metadata_value in getattr(routing_metadata, metadata_attrib):
                    if metadata_value:
                        # Loop thru matching-config values of a particular type (e.g. "domains" or "emails" etc )
                        for match_param_value in match_params_list:
                            # compare the match_param_value and metadata_value using the relevant matching function
                            match_success = match_func(match_param_value, metadata_value)
                            if match_success:
                                # we have a match - create provenance object
                                prov = MatchProvenance()
                                prov.repo_id = repo_id
                                prov.add_provenance(
                                    match_param_type, match_param_value, metadata_attrib, metadata_value, match_success
                                )
                                # we've successfully made a match, so return the populated provenance object
                                return prov

    # if we reach this point, we've failed to make a match so return None
    return None


def repackage(unrouted, packaging_types):
    """
    Repackage any binary content associated with the notification according to the list of required packaging types.

    Note that this takes an unrouted notification, because of the point in the routing workflow at
    which it is invoked, although in reality you could also pass it any of the other fully fledged
    notification objects such as RoutedNotification

    For each packaging type we generate the required package (for example, SimpleZip) and/or  unpack particular files
    to suit the needs of the repositories

    For each successful conversion the notification recieves a new link attribute containing
    identification information for the converted package.

    :param unrouted: notification object
    :param packaging_types: set of required packaging types

    :return: a list of the format conversions that were carried out (each list element is a dict of information)
    """
    # if there's no package format, it means this notification has no package file (i.e. it is a meta-data only
    # notification) so there's no repackaging to be done
    unrouted_pkg_format = unrouted.packaging_format
    if unrouted_pkg_format is None:
        return []

    unrouted_pkg_mgr = packages.PackageFactory.get_handler_class(unrouted_pkg_format)
    conversions = []  # List of conversions required
    unpack_list = []  # List of unpacking required
    # Iterate through the unique packaging types, each will correspond to either a conversion or an unpacking
    for pkg_type in packaging_types:
        # if the package manager can convert to required package type then store in the conversions list
        if unrouted_pkg_mgr.convertible(pkg_type):
            conversions.append(pkg_type)

        # Or, if we want to unpack the zip file, add to the unpack list.
        # Unpacking is a special case where the target repository wants to "pull" individual files via URL. In that
        # case the package must be unpacked so that individual files exist to be pulled.
        elif pkg_type in UnpackUtil.unpacked_handler_dict:
            unpack_list.append(pkg_type)

    # At this point we have a de-duplicated list of all formats that we need to convert
    # the package to, that the package is capable of converting itself into.
    # We also have a list of unpackaged formats that we will need to unpack to.
    unrouted_id = unrouted.id
    if conversions:
        # Convert the original package to all the formats needed to satisfy all the repositories that the
        # notification (and its package) have been routed to
        converted = packages.PackageManager.convert(unrouted_id, unrouted_pkg_format, conversions)
        links = [
            {
                "type": "package",
                "format": "application/zip",
                "access": "router",
                "cloc": filename,
                "packaging": pkg_format
            } for pkg_format, filename in converted
        ]
    else:
        links = []
    # If any unpacking required (for those repositories that want to "pull" the files)
    if unpack_list:
        # results from unpacker is a list of link dicts
        links += UnpackUtil.unpacker(unrouted_id, unrouted_pkg_mgr.zip_name(), unpack_list)

    if current_app.config.get("LOG_DEBUG"):
        current_app.logger.debug(f"Repackaged content for note {unrouted_id} - Links: {str(links)}")
    return links


