"""
Functions which generate reports from the JPER system

"""
import os
from json import dump
from octopus.lib.csv_files import create_csv_file
from octopus.lib.dates import now_str

from router.shared.models.account import AccOrg, AccRepoMatchParams, REPO_MATCH_PARAM_SCROLL_NUM, CONN_CLOSE, DICT
from router.shared.models.note import RoutedNotification, ROUTED_ALL_SCROLL_NUM
from router.shared.models.harvester import HarvesterWebserviceModel
from router.jper.models.reports import MonthlyInstitutionStats, MonthlyPublisherStats, MonthlyHarvesterStats
from router.jper.models.publisher import PublisherDepositRecord
from router.jper.pub_testing import validate_aff_org_value

month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


def column_month_headers(*args):
    """
    Helper function which takes a series of arguments and returns a list of the form
    ["Jan " + arg[0], "Jan " + arg[1], "Jan " + arg[2], ... , "Jan " + arg[n], "Feb " + arg[0], "Feb + arg[1]", ...
    "Dec " + arg[n]]
    This list is to be used as a series of column headers in a report
    For example ["Jan received", "Jan matched", "Feb received", "Feb matched", ... , "Dec received", "Dec matched"]
    this would be the output of column_month_headers("received", "matched")

    :param args: the arguments we wish to append to the month names
    :return: the list as described in the function description
    """
    return [f"{month} {column_name}" for month in month_names for column_name in args]


def generate_institutions_report(first_date, last_date, report_file_path, live_file=False):
    """
    Generates an Annual report on number of notifications sent to various institution repositories.
    Will either be for test repositories or live repositories depending on value of 'live_file' parameter.

    first_date is 1st January of required year.
    last_date is 1st Dec of required year.


    :param first_date: Date object - Jan 1st YYYY
    :param last_date: Date object - Dec 1st YYYY
    :param report_file_path: String - file path for existing/new report to be output
    :param live_file: Boolean - True: Report on institutions Live within the report period
                                False: Report on institutions that are in Test mode during the report period
    :return:
    """

    all_csv_rows = [["HEI", "Jisc ID", "Repository", "Live Date"] + column_month_headers("metadata", "content", "Total")]
    totals = {m: [0, 0, 0] for m in month_names}
    sorted_list_dicts = MonthlyInstitutionStats.get_stats_between_2_dates("L" if live_file else "T",    # Live or Test
                                                                          first_date,
                                                                          last_date)
    org_row = True
    for org_dict in sorted_list_dicts:
        # The last dict, with ID of 0, contains the Unique values: need to write the totals row before that row
        if org_dict["id"] == 0:
            org_row = False
            # Need to print the totals row first
            data_row = ["Total", "", "", ""]
            for m in month_names:
                data_row += totals[m]
            all_csv_rows.append(data_row)

        data_row = [org_dict["name"], org_dict.get("jisc_id", ""), org_dict.get("repo", ""), org_dict.get("live_date", "")]
        for month in month_names:
            meta, content = org_dict.get(month, (0, 0))
            total = meta + content
            # If not Unique row and total is not zero then need to accumulate totals
            if org_row and total:
                month_totals = totals[month]
                month_totals[0] += meta
                month_totals[1] += content
                month_totals[2] += total
            data_row += [meta, content, total]
        all_csv_rows.append(data_row)

    # Create report file
    create_csv_file(report_file_path, all_csv_rows)


def produce_pub_harv_report(pub_or_harv, sorted_list_dicts, report_file_path):
    """

    :param pub_or_harv: String - "Publisher" or "Harvester"
    :param sorted_list_dicts: List of dicts - data returned by db query
    :param report_file_path: String - filepath
    :return:
    """
    all_csv_rows = [[pub_or_harv] + column_month_headers("received", "matched")]
    totals = {m: [0, 0] for m in month_names}
    for org_dict in sorted_list_dicts:
        data_row = [org_dict["name"]]
        for month in month_names:
            received, matched = org_dict.get(month, (0, 0))
            if received:
                month_totals = totals[month]
                month_totals[0] += received
                month_totals[1] += matched
            data_row += [received, matched]
        all_csv_rows.append(data_row)

    # Create totals row
    data_row = ["Total"]
    for m in month_names:
        data_row += totals[m]
    all_csv_rows.append(data_row)

    # Create report file
    create_csv_file(report_file_path, all_csv_rows)


def generate_publisher_report(first_date, last_date, report_file_path):
    """
    Generates annual report on publisher ftp submission statistics (# of successful and # of matched submissions).

    :param first_date: Date object - Jan 1st YYYY
    :param last_date: Date object - Dec 1st YYYY
    :param report_file_path: the path to the report we wish to edit/create
    """
    produce_pub_harv_report("Publisher",
                            MonthlyPublisherStats.get_stats_between_2_dates(first_date, last_date),
                            report_file_path
                            )


def generate_harvester_report(first_date, last_date, report_file_path):
    """
    Generates annual harvester submission statistics report (# of successfully harvested notifications and # of matched
    notifications).
    :param first_date: Date object - Jan 1st YYYY
    :param last_date: Date object - Dec 1st YYYY
    :param report_file_path: the path to the report we wish to edit/create
    """
    produce_pub_harv_report("Harvester",
                            MonthlyHarvesterStats.get_stats_between_2_dates(first_date, last_date),
                            report_file_path
                            )


def generate_all_publisher_doi_to_repos_reports(first_date, last_date, reports_dir):
    """
    Generates CSV report for publisher of distribution of deposited articles to repositories.
    :param first_date: Date object - Jan 1st YYYY
    :param last_date: Date object - Dec 1st YYYY
    :param reports_dir: Directory to place report
    :return: List of Tuples [(recipient-emails-list, report-path, org-name), ...]
    """
    # Create map of Live repository org-ids to org-name (close cursor after use, as we only call this function monthly)
    live_repo_id_to_orgname_dict = AccOrg.get_account_id_to_org_names_dict("R", live_test="L", close_cursor=True)

    # We create reusable DOI_scroller here, only so that we can call detach_n_close() after the processing loop
    # (The reusable scroller is called repeatedly within get_pub_doi_repo_csv_data())
    pub_doi_scroller = RoutedNotification.get_pub_doi_repo_data_between_2_dates_scroller(None, None, None)
    reports_created = []
    yymm_str = first_date.strftime("%Y-%m")
    for pub_acc in AccOrg.get_publishers():
        pub_data = pub_acc.publisher_data
        report_format = pub_data.report_format
        # Only produce report if report_format is NOT empty string (meaning report NOT required)
        if report_format:
            publisher_doi_report_dir = f"{reports_dir}/{pub_acc.uuid}"
            if not os.path.exists(publisher_doi_report_dir):
                os.makedirs(publisher_doi_report_dir)
            report_file_path = f"{publisher_doi_report_dir}/doi_distribution_{yymm_str}.csv"
            # Create report file
            create_csv_file(report_file_path,
                             RoutedNotification.get_pub_doi_repo_csv_data(
                                 pub_acc.id, first_date, last_date, report_format, live_repo_id_to_orgname_dict))
            reports_created.append((pub_data.report_emails, report_file_path, pub_acc.org_name))

    # Close the reusable scroller (close database connection & cursor)
    pub_doi_scroller.detach_n_close()

    return reports_created


def generate_duplicate_submissions_report(from_date, to_date, report_file_path=None, return_data=False):
    """
    Generates report showing number of duplicate submissions over the specified period.

    If report_file_path is provided then a CSV file will be created.

    Function will return either the data_rows list or the data_row_count depending on the values of parameters:
    report_file_path & return_data.

    :param from_date: String "YYYY-MM-DD" - Earliest date to produce report for.
    :param to_date: String "YYYY-MM-DD" - Latest date to produce report for.
    :param report_file_path: the path to the report we wish to create
    :param return_data: What to return if report_file_path is NOT None: return data list or data_count
    :return: Either number of rows of data written to `report_file_path` (if it is not None and return_data is False)
             or list of csv_data.
    """
    csv_data = []
    data_count = 0
    # Run query to get basic info about duplicates - this returns list of lists like:
    # [[dup_count-Int, pub_id-Int, doi-Str, file_names-Str, deposit_dates-Str, note_ids-Str, metrics-Str, repo_ids-Int-List], ...]
    duplicates_recs = PublisherDepositRecord.duplicate_doi_query(from_date=from_date, to_date=to_date, days_margin=7)
    if duplicates_recs:
        # Need to convert Pub-ID and Repo-IDs into corresponding Organisation Names
        org_name_dict = AccOrg.get_account_id_to_org_names_dict("PR", live_test="LT")

        for dup_count, pub_id, doi, file_names, deposit_dates, note_ids, metrics, repo_ids_list in duplicates_recs:
            csv_data.append([
                dup_count,
                org_name_dict.get(pub_id, "UNKNOWN"),
                doi,
                file_names,
                deposit_dates,
                "; ".join(sorted([org_name_dict.get(id_, "UNKNOWN") for id_ in repo_ids_list], key=str.upper)),
                note_ids,
                metrics
            ])

    if report_file_path:
        # Create report file
        data_count = create_csv_file(
            report_file_path,
            csv_data,
            heading_row=["Duplicate count", "Publisher", "DOI", "Filenames", "Deposit Dates", "Target Repositories",
                         "Notification IDs",
                         "Metrics: bit_field|auths|orcids|funders|fund-ids|grants|licenses|struct-affs|aff-ids"]
        )
    return csv_data if return_data or not report_file_path else data_count


def note_types_report(log_file_pathname=None, print_it=False):
    """
    Analyse all notifications in database to determine range of `type` values for particular fields.

    :param log_file_pathname: [OPTIONAL] String - output file path
    :param print_it: Boolean - True: print output to terminal; False: no terminal output
    :return: Tuple (output-file-path, record count)
    """
    def write_log(*args):
        if print_it:
            print(*args)
        log_file.write("".join(args))

    def format_output(_set, sep="\n  "):
        return sep + sep.join(sorted(_set)) + "\n"

    if log_file_pathname is None:
        log_file_pathname = os.path.join("/tmp", f"notification_types_analysis_{now_str('%Y-%m-%d')}.txt")
    try:
        log_file = open(log_file_pathname, "w", encoding="utf-8")
    except Exception as e:
        msg = f"Failed to open log file {log_file_pathname}. {repr(e)}"
        if print_it:
            print(msg)
        raise Exception(msg)

    if print_it:
        print(f"\nResults will be written to file: {log_file_pathname}\n")

    repos = {"pub": "ALL Publishers", "harv": "ALL Harvesters"}
    art_types = {"pub": set(), "harv": set()}
    article_version = set()
    author_type = set()
    contrib_type = set()
    hist_date_type = set()
    journ_id_type = set()
    art_id_type = set()
    aff_id_type = set()
    fund_id_type = set()

    NONE = "''"  # …
    count = 0

    scroller = RoutedNotification.routed_scroller_obj(scroll_num=ROUTED_ALL_SCROLL_NUM)
    with scroller:
        for note in scroller:
            count += 1
            if (count % 1000) == 0 and print_it:
                print(f"Processed {count}")
            art_type = note.article_type or NONE
            #  Detailed breakdown of article type by publisher
            pub_id = note.provider_id
            # Add to all publisher or all harvesters
            art_types["pub" if pub_id else "harv"].add(art_type)  # All publishers or harvesters

            pub_type = f"p{pub_id}" if pub_id else f"h{note.provider_harv_id}"
            if pub_type not in repos:
                repos[pub_type] = note.provider_agent
            try:
                art_types[pub_type].add(art_type)
            except KeyError:
                art_types[pub_type] = {art_type}    # Create new set

            article_version.add(note.article_version or NONE)
            for auth in note.authors:
                author_type.add(auth.get("type", NONE))
                for aff in auth.get("affiliations", []):
                    for id_ in aff.get("identifier", []):
                        aff_id_type.add(id_.get("type"))
            for contrib in note.contributors:
                contrib_type.add(contrib.get("type", NONE))
            for hist_date in note.history_date:
                hist_date_type.add(hist_date.get("date_type", NONE))
            for _id in note.journal_identifiers:
                journ_id_type.add(_id.get("type"))
            for _id in note.article_identifiers:
                art_id_type.add(_id.get("type"))
            for fund in note.funding:
                for _id in fund.get("identifier", []):
                    fund_id_type.add(_id.get("type"))

    write_log(f"\n**** Results from Analysing {count} Notifications on {now_str('%d/%m/%Y')} ****\n\n")
    # write_log(f"Article types: {format_output(article_type)}")
    write_log("\n", "Article version:", format_output(article_version))
    write_log("\n", "Author types:", format_output(author_type))
    write_log("\n", "Contributor types:", format_output(contrib_type))
    write_log("\n", "History date types:", format_output(hist_date_type))
    write_log("\n", "Journal ID types:", format_output(journ_id_type))
    write_log("\n", "Article ID types:", format_output(art_id_type))
    write_log("\n", "Affiliation ID types:", format_output(aff_id_type))
    write_log("\n", "Funding ID types:", format_output(fund_id_type))

    write_log("\n*** Article types by provider ***\n")
    for k, s in art_types.items():
        write_log(f"\nArticle types - {repos[k]}:", format_output(s))

    write_log("\n*** Resource Type (Category) Analysis ***\n")
    for k in ("pub", "harv"):
        write_log(f"\n* {repos[k]} *\n")
        for art_type in art_types[k]:
            code = RoutedNotification.calc_category_from_article_type(art_type)
            desc = RoutedNotification.decode_category(code)
            write_log(f" {code}: {desc} -- {art_type}\n")

    log_file.close()
    return log_file_pathname, count


def provider_aff_usage_report(csv_file_pathname=None, print_it=False):
    """
    Analyse all notifications in database to determine how providers provide affiliations.

    Report:
        Total no of notifications each of them provided in last 90 days; then, from these…
        Total no of author affiliations these contained; of these…
        % of affiliations that lack org
        % of affiliations that have none of org, city, country.
        % of affiliations that lack org ID.
        % of affiliations that have neither org nor org ID.
        % of affiliations that have none of org, city, country, org ID.
    List the providers in decreasing order of (3) above.

    :param csv_file_pathname: [OPTIONAL] String - output file path
    :param print_it: Boolean - True: print output to terminal; False: no terminal output
    :return: Tuple (output-file-path, record count)
    """
    if csv_file_pathname is None:
        csv_file_pathname = os.path.join("/tmp", f"provider_aff_usage_{now_str('%Y-%m-%d')}.csv")

    if print_it:
        print(f"\nResults will be written to file: {csv_file_pathname}\n")

    pub_data_dict = {}      # Statistics keyed by Publisher ID
    harv_data_dict = {}      # Statistics keyed by Harvester ID
    count = 0

    ## SCROLL THROUGH ALL NOTIFICATIONS - populate `pub_data_dict` or `harv_data_dict` with statistics ##
    scroller = RoutedNotification.routed_scroller_obj(scroll_num=ROUTED_ALL_SCROLL_NUM)
    with scroller:
        for note in scroller:
            count += 1
            if (count % 1000) == 0 and print_it:
                print(f"Processed {count}")
            # if (count % 100) == 0:
            #     break

            prov_id = note.provider_id      # publisher-Id
            if prov_id:
                # Publisher notification
                data_dict = pub_data_dict
            else:
                # Harvester notification
                prov_id = note.provider_harv_id     # harvester-Id
                data_dict = harv_data_dict
            num_aff = 0
            no_org = 0
            no_id = 0
            no_org_id = 0
            no_org_city_county = 0
            no_org_city_county_id = 0
            for auth in note.authors:
                for aff in auth.get("affiliations", []):
                    num_aff += 1
                    aff_org = aff.get("org")
                    aff_city = aff.get("city")
                    aff_country = aff.get("country")
                    aff_ids = aff.get("identifier")
                    if not aff_org:
                        no_org += 1
                        if not aff_ids:
                            no_org_id += 1
                        if not aff_city and not aff_country:
                            no_org_city_county += 1
                            if not aff_ids:
                                no_org_city_county_id += 1
                    if not aff_ids:
                        no_id += 1
            try:
                prov_dict = data_dict[prov_id]
            except KeyError:
                prov_dict = data_dict[prov_id] = {
                    "num_notes": 0, "num_aff": 0, "no_org": 0, "no_id": 0, "no_org_id": 0, "no_occ": 0, "no_occ_id": 0
                }
            prov_dict["num_notes"] += 1
            prov_dict["num_aff"] += num_aff
            prov_dict["no_org"] += no_org
            prov_dict["no_id"] += no_id
            prov_dict["no_org_id"] += no_org_id
            prov_dict["no_occ"] += no_org_city_county
            prov_dict["no_occ_id"] += no_org_city_county_id
            # if prov_id in [151]:
            #     print(prov_id, note.id)

    ## Create provider lookup dict ##

    # Dict {pub-id: publisher-name} of all Live publishers
    pub_name_dict = AccOrg.get_account_id_to_org_names_dict("P", live_test="L", close_cursor=True)
    # Dict for harvesters
    harv_name_dict = {rec["id"]: rec["name"] for rec in HarvesterWebserviceModel.get_webservices_dicts()}

    ## Create list of Provider statistics for outputting to CSV file ##

    # Create a list of lists of provider information
    # [[pub_or_harv, prov_id, prov_name, tot_notes, tot_affs, perc_no_org, perc_no_id, perc_no_org_id, perc_no_occ, perc_no_occ_id], ...]
    live_prov_list = []
    for pub_harv, data_dict, name_dict in (("P", pub_data_dict, pub_name_dict), ("H", harv_data_dict, harv_name_dict)):
        for prov_id, prov_dict in data_dict.items():
            provider_name = name_dict.get(prov_id)
            # if provider name is none it means we have a Test (or Deleted, unlikely) provider - so we ignore it
            if provider_name:
                num_aff = prov_dict["num_aff"]
                prov_list = [pub_harv, prov_id, provider_name, prov_dict["num_notes"], num_aff] + [round(100 * prov_dict[k] / num_aff, 2) for k in ("no_org", "no_id", "no_org_id", "no_occ", "no_occ_id")]
                live_prov_list.append(prov_list)

    # Sort by percentage with no organisation value
    live_prov_list.sort(key=lambda x: x[5], reverse=True)

    ## Create CSV file of results ##
    headings = ["Pub. or Harv.", "Provider ID", "Provider Name", "Total Notifications", "Total Affiliations", "% No Org", "% No ID", "% No Org & ID", "% No Org & City & Country", "% No Org & City & Country & ID"]
    num_recs = create_csv_file(csv_file_pathname, live_prov_list, headings)

    if print_it:
        print(f"\nResults have been written to files: {csv_file_pathname}.\n")

    return csv_file_pathname, count


def provider_aff_org_report(csv_file_pathname=None, print_it=False):
    """
    Analyse all notifications in database to determine proportion of problematic affiliation <org> values.

    Report:
        Total no of notifications each of them provided in last 90 days; then, from these…
        Total no of authors
        Total no of author affiliations these contained; of these…
        % of affiliations with an org field
        % of affiliations with a questionable org field (may contain more than org name)
     List the providers in decreasing order of (5) above.

    :param csv_file_pathname: [OPTIONAL] String - output file path
    :param print_it: Boolean - True: print output to terminal; False: no terminal output
    :return: Tuple (output-file-path, record count)
    """
    if csv_file_pathname is None:
        csv_file_pathname = os.path.join("/tmp", f"provider_dubious_aff_org_{now_str('%Y-%m-%d')}.csv")

    if print_it:
        print(f"\nResults will be written to file: {csv_file_pathname}\n")

    pub_data_dict = {}      # Statistics keyed by Publisher ID
    harv_data_dict = {}      # Statistics keyed by Harvester ID
    count = 0

    ## SCROLL THROUGH ALL NOTIFICATIONS - populate `pub_data_dict` or `harv_data_dict` with statistics ##
    scroller = RoutedNotification.routed_scroller_obj(scroll_num=ROUTED_ALL_SCROLL_NUM)
    with scroller:
        for note in scroller:
            count += 1
            if (count % 1000) == 0 and print_it:
                print(f"Processed {count}")
            # if (count % 100) == 0:
            #     break

            prov_id = note.provider_id      # publisher-Id
            if prov_id:
                # Publisher notification
                data_dict = pub_data_dict
            else:
                # Harvester notification
                prov_id = note.provider_harv_id     # harvester-Id
                data_dict = harv_data_dict
            num_auth = 0
            num_aff = 0
            num_org = 0
            num_iffy_org = 0
            for auth in note.authors:
                num_auth += 1
                for aff in auth.get("affiliations", []):
                    num_aff += 1
                    aff_org = aff.get("org")
                    if aff_org:
                        num_org += 1
                        # If questionable <org> value
                        if validate_aff_org_value(aff_org) is not None:
                            num_iffy_org += 1
            try:
                prov_dict = data_dict[prov_id]
            except KeyError:
                prov_dict = data_dict[prov_id] = {
                    "num_notes": 0, "num_auth": 0, "num_aff": 0, "num_org": 0, "num_iffy_org": 0
                }
            prov_dict["num_notes"] += 1
            prov_dict["num_auth"] += num_auth
            prov_dict["num_aff"] += num_aff
            prov_dict["num_org"] += num_org
            prov_dict["num_iffy_org"] += num_iffy_org
            # if prov_id in [151]:
            #     print(prov_id, note.id)

    ## Create provider lookup dict ##

    # Dict {pub-id: publisher-name} of all Live publishers
    pub_name_dict = AccOrg.get_account_id_to_org_names_dict("P", live_test="L", close_cursor=True)
    # Dict for harvesters
    harv_name_dict = {rec["id"]: rec["name"] for rec in HarvesterWebserviceModel.get_webservices_dicts()}

    ## Create list of Provider statistics for outputting to CSV file ##

    # Create a list of lists of provider information
    # [[pub_or_harv, prov_id, prov_name, tot_notes, tot_affs, perc_no_org, perc_no_id, perc_no_org_id, perc_no_occ, perc_no_occ_id], ...]
    live_prov_list = []
    for pub_harv, data_dict, name_dict in (("P", pub_data_dict, pub_name_dict), ("H", harv_data_dict, harv_name_dict)):
        for prov_id, prov_dict in data_dict.items():
            provider_name = name_dict.get(prov_id)
            # if provider name is none it means we have a Test (or Deleted, unlikely) provider - so we ignore it
            if provider_name:
                num_aff = prov_dict["num_aff"]
                prov_list = [pub_harv, prov_id, provider_name, prov_dict["num_notes"], prov_dict["num_auth"], num_aff] + [round(100 * prov_dict[k] / num_aff, 2) for k in ("num_org", "num_iffy_org")]
                live_prov_list.append(prov_list)

    # Sort by last column
    live_prov_list.sort(key=lambda x: x[-1], reverse=True)

    ## Create CSV file of results ##
    headings = ["Pub. or Harv.", "Provider ID", "Provider Name", "Total Notifications", "Total Authors", "Total Affiliations", "% With Org", "% Dubious Org"]
    num_recs = create_csv_file(csv_file_pathname, live_prov_list, headings)

    if print_it:
        print(f"\nResults have been written to files: {csv_file_pathname}.\n")

    return csv_file_pathname, count


def matching_params_report(csv_file_pathname=None, print_it=False, sep=",  "):
    """
    Produce a summary of all matching parameters.

    Report:
        Organisation name
        Params rec ID
        Params last updated timestamp
        Regex currently used in name variants
        Regex previously used in name variants
        Number of archived records
        Name variants
        Organisation IDs
        Domains
        Post codes
        Count of Grant numbers
        Count of ORCIDs


    :param csv_file_pathname: [OPTIONAL] String - output file path
    :param print_it: Boolean - True: print output to terminal; False: no terminal output
    :param sep: String - Separator to use when JOINing list contents
    :return: Tuple (output-file-path, record count)
    """

    def list_to_str(list_, sep):
        if list_:
            return sep.join(list_)
        else:
            return ""


    if csv_file_pathname is None:
        csv_file_pathname = os.path.join("/tmp", f"all_matching_parameters.csv")

    if print_it:
        print(f"\nResults will be written to file: {csv_file_pathname}\n")


    # Dict of tuples (Org-name, archived-rec-count), keyed by account-ID
    repo_dict = {ac_id: (org_name, archived_count) for org_name, ac_id, ac_uuid, status, updated, has_regex, had_regex, archived_count
                 in AccRepoMatchParams.get_summary_info()}
    data_list = []
    match_param_scroller = AccRepoMatchParams.scroller_obj(
        pull_name="all_repo", scroll_num=REPO_MATCH_PARAM_SCROLL_NUM, end_action=CONN_CLOSE)
    with match_param_scroller:
        for mp in match_param_scroller:
            org_name, archive_count = repo_dict.get(mp.id, ('MISSING', 0))
            data_list.append((
                org_name,
                mp.id,
                mp.last_updated_formatted(),
                "Yes" if mp.has_regex else "",
                "Yes" if mp.had_regex else "",
                archive_count,
                list_to_str(mp.name_variants, sep),
                list_to_str(mp.formatted_org_ids, sep),
                list_to_str(mp.domains, sep),
                list_to_str(mp.postcodes, sep),
                len(mp.grants),
                len(mp.author_orcids)
            ))
    del match_param_scroller  # Delete here to clear down any memory

    data_list.sort(key=lambda row: row[0])
    ## Create CSV file of results ##
    headings = ["Org Name", "Rec ID", "Last Updated", "Regex used", "Regex previously used", "Num archived params", "Name Variants", "Organisation IDs", "Domains", "Postcodes", "Num. Grants", "Num ORCIDs"]
    num_recs = create_csv_file(csv_file_pathname, data_list, headings)

    if print_it:
        print(f"\nResults have been written to files: {csv_file_pathname}.\n")

    return csv_file_pathname, num_recs

def matching_params_json(json_file_pathname=None, print_it=False, indent=4):
    """
    Produce JSON output of all matching parameters.

    :param json_file_pathname: [OPTIONAL] String - output file path
    :param print_it: Boolean - True: print output to terminal; False: no terminal output
    :param indent: Integer - Number of characters to indent
    :return: Tuple (output-file-path, record count)
    """

    def delete_dict_fields(_dict, fields):
        """
        Attempt to delete elements from dict, ignore KeyError (field not in dict)
        """
        for _field in fields:
            try:
                del _dict[_field]
            except KeyError:
                pass

    if json_file_pathname is None:
        json_file_pathname = os.path.join("/tmp", f"all_matching_parameters.json")

    if print_it:
        print(f"\nResults will be written to file: {json_file_pathname}\n")

    repo_acc_ids_dict = AccOrg.get_account_id_to_org_names_dict("R", live_test="LT", close_cursor=True)
    data_list = []
    num_recs = 0
    match_param_scroller = AccRepoMatchParams.scroller_obj(
        pull_name="all_repo", rec_format=DICT, scroll_num=REPO_MATCH_PARAM_SCROLL_NUM, end_action=CONN_CLOSE)
    with match_param_scroller:
        for mp_dict in match_param_scroller:
            mp_id = mp_dict["id"]
            delete_dict_fields(mp_dict, ("id", "created", "updated"))
            mp_dict["org_name"] = repo_acc_ids_dict.get(mp_id, 'MISSING')
            mp_dict["has_regex"] = mp_dict["has_regex"] == 1
            mp_dict["had_regex"] = mp_dict["had_regex"] == 1
            data_list.append(mp_dict)
            num_recs += 1
    del match_param_scroller  # Delete here to clear down any memory


    data_list.sort(key=lambda row: row["org_name"])
    ## Create json file of results ##
    with open(json_file_pathname, "w", encoding='utf-8') as json_file:
        dump(data_list, json_file, indent=indent)
    if print_it:
        print(f"\nResults have been written to files: {json_file_pathname}.\n")

    return json_file_pathname, num_recs
