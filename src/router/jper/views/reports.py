"""
Blueprint for providing reports UI
"""

import os
import re
from flask import Blueprint, render_template, redirect, send_from_directory, current_app, url_for, request, flash
from flask_login import current_user
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from octopus.lib.dates import ymd_to_dmy, now_str
from router.shared.models.doi_register import DoiRegister
from router.shared.models.metrics import MetricsRecord
from router.shared.models.schedule import Job
from router.jper.reports import generate_duplicate_submissions_report, matching_params_report, matching_params_json
from router.jper.forms.reports import MiscReportScriptsForm

blueprint = Blueprint('reports', __name__)

regex_csv_txt_or_json_file = re.compile(r'\.(?:csv|txt|json)$')

MISC_DIR = "misc"
DUP_SUBMISSIONS_DIR = "dup_submission"


def _get_report_files_from_dir(directory):
    """
    Private function, returns a list of reports in a given file directory, sorted on year, returns empty list if no
    files are present in the given directory

    :param directory: the directory we wish to return files for

    :return: the list of reports
    """
    try:
        reports = [fl for fl in os.listdir(directory) if regex_csv_txt_or_json_file.search(fl)]
        reports.sort(reverse=True)
    except Exception:
        reports = []
    return reports


def _report_directory(report_type=None):
    """
    Private function, gives the repository path given a certain report_type. If empty, just pass base repository path.

    :param report_type: The type of report, for example "publishers"

    :return: The full file path, appended if report_type not None.
    """
    report_directory = current_app.config.get('REPORTSDIR', '/var/pubrouter/reports')
    if report_type:
        report_directory = os.path.join(report_directory, report_type)
    return report_directory


def _partition_reports(partition_func, report_type=None):
    """
    Partition report files in a directory by a given partition function, returning two lists of filenames.

    The partition function parameter should expect a filename and return a boolean based on that filename.

    :param partition_func: Any function that takes one variable(filename) and returns a boolean.
    :param report_type: The type of report, for example "publishers"

    :return: Two lists of filenames, the first where the partition_func returned True, the second where it returned
    False.
    """
    true_partition = []
    false_partition = []
    for filename in _get_report_files_from_dir(_report_directory(report_type)):
        if partition_func(filename):
            true_partition.append(filename)
        else:
            false_partition.append(filename)
    return true_partition, false_partition


def _get_institution_report_filenames():
    """
    Partition the reports in the main directory by names which include "LIVE" and ones that do not
    (which will be the test reports.)

    :return: Two lists of report filenames - The first list is LIVE institution reports,
    the second is TEST institution reports.
    """
    return _partition_reports(lambda filename: "LIVE" in filename)


def _get_publisher_and_harvester_report_filenames():
    """
    Partition the reports in the publishers directory by names which include "publishers" and ones that do not
    (which will be the harvester reports.)

    :return: Two lists of report filenames - the first list is publisher reports, the second is harvester reports.
    """
    return _partition_reports(lambda filename: "publishers" in filename, "publishers")


@blueprint.before_request
def restrict():
    if current_user.is_anonymous:
        return redirect(url_for('account.login'))
    elif not current_user.acc_org.is_super:
        return redirect(url_for('index'))


@blueprint.route('/')
def index():
    # Get all sets of reports, and use this to create our index page which presents the sets of reports
    # separated by headers
    live_institution_reports, test_institution_reports = _get_institution_report_filenames()
    publisher_reports, harvester_reports = _get_publisher_and_harvester_report_filenames()
    return render_template(
        'reports/index.html',
        title='Reports',
        live_institution_reports=live_institution_reports,
        test_institution_reports=test_institution_reports,
        publisher_reports=publisher_reports,
        harvester_reports=harvester_reports,
        duplicate_reports=_get_report_files_from_dir(_report_directory(DUP_SUBMISSIONS_DIR)),
        misc_reports=_get_report_files_from_dir(_report_directory(MISC_DIR)),
    )


@blueprint.route('/publishers')
def publishers():
    # Get the list of reports on publishers from our report directories
    publisher_reports, _ = _get_publisher_and_harvester_report_filenames()
    return render_template(
        'reports/reports.html',
        title='Publisher reports',
        reports=publisher_reports,
        report_type="Publisher",
        path_prefix="publishers"
    )


@blueprint.route('/harvester')
def harvester():
    # Get the list of harvester reports from our report directories
    _, harvester_reports = _get_publisher_and_harvester_report_filenames()
    return render_template(
        "reports/reports.html",
        title='Harvester reports',
        reports=harvester_reports,
        report_type="Harvester",
        path_prefix="publishers"
    )


@blueprint.route('/institutions')
def institutions():
    # Get the list of reports on LIVE institutions from our report directories
    institution_reports, _ = _get_institution_report_filenames()
    return render_template(
        'reports/reports.html',
        title='Live institution reports',
        reports=institution_reports,
        report_type="Live institution"
    )


@blueprint.route('/test-institutions')
def test_institutions():
    # Get the list of reports on TEST institutions from our report directories
    _, institution_reports = _get_institution_report_filenames()
    return render_template(
        'reports/reports.html',
        title='Test institution reports',
        reports=institution_reports,
        report_type="Test institution"
    )


@blueprint.route('/dup_submission_reports')
def dup_submission_reports():
    return render_template(
        'reports/reports.html',
        title='Duplicate submissions monthly reports',
        reports=_get_report_files_from_dir(_report_directory(DUP_SUBMISSIONS_DIR)),
        report_type="Duplicate submissions monthly",
        path_prefix=DUP_SUBMISSIONS_DIR,
        info_html="""
        	<p>These reports shows duplicate submissions (by DOI) from publishers where at least 1 duplicate was  routed to at least 1 live repository account within the specified month.</p>
			<p>In order to capture duplicates that may have occurred close to the start or end of the month, the database is actually searched over a date range 7 days either side of the month.</p>
			<p>In the results, the <i>metadata metrics</i> strings comprise a bit_field value, followed by counts of attributes:<br><span class="strong smallish">bit_field | authors | orcids | funders | funder-ids | grants | licenses | structured-affiliations | affiliation-ids</span>.<br>Multiple metrics strings for a particular DOI indicates substantial metadata differences among the duplicates; whereas a single metrics string suggests minimal or no differences in metadata.</p>
        """
    )


@blueprint.route('/past_misc_reports')
def past_misc_reports():
    # avail_reports = "</li><li>".join([f"{k}: {v[0]}" for k, v in MiscReportScriptsForm.report_info.items()])
    avail_reports = "</li><li>".join([f"<b>{v[4].format('…')}</b> - {v[0]}" for v in MiscReportScriptsForm.report_info.values()])
    return render_template(
        'reports/reports.html',
        title='Ad hoc miscellaneous reports',
        reports=_get_report_files_from_dir(_report_directory(MISC_DIR)),
        report_type="Ad hoc miscellaneous",
        path_prefix=MISC_DIR,
        info_html=f"<p>The following, previously run, ad hoc reports may be available:</p><ul><li>{avail_reports}.</li></ul>"
    )


# for all other arguments, store this in variable path using werkzeug's path converter, to ensure that slashes are
# stored as expected http://werkzeug.pocoo.org/docs/0.14/routing/#werkzeug.routing.PathConverter
@blueprint.route('/<path:path>')
def serve_report(path):
    """
    Takes a path which doesn't fit the other views and attempts to send the file of it's path name to the requester
    """
    # combine the path name with the report's repository path to get a full path to the file
    # then split into the directory path and the filename, for use in send_from_directory
    reports_dir, filename = os.path.split(os.path.join(_report_directory(), path))
    # attempt to send the file from the calculated directory path and filename
    return send_from_directory(reports_dir, filename, as_attachment=True)


@blueprint.route('/routed_in_period')
def routed_in_period():
    """
    Report on unique articles matched to institutions in defined period
    :return:
    """
    data_list = []
    earliest_date = "2021-06-05"
    earliest_date_dmy = "05-06-2021"

    from_date = request.args.get("from_date")
    to_date = request.args.get("to_date")

    # if at least 1 date is set
    # If one or both of from_date & to_date are empty, we need to set defaults
    if from_date or to_date:
        if not to_date:
            # 1 year after from_date
            to_date = (datetime.strptime(from_date, "%Y-%m-%d") + relativedelta(months=12, days=-1)).strftime("%Y-%m-%d")
        elif not from_date:
            # 1 year before to_date
            from_date = (datetime.strptime(to_date, "%Y-%m-%d") - relativedelta(months=12, days=-1)).strftime("%Y-%m-%d")

        # Need to report error if From date is before earliest allowed date
        if from_date < earliest_date:
            flash(
                f"The from-date ({ymd_to_dmy(from_date)}) that you input is before the earliest date ({earliest_date_dmy}) for which data is available and so has been changed to that. ",
                'info')
            from_date = earliest_date

        if from_date > to_date:
            flash(
                f"The from-date ({from_date}) is later than the to-date ({to_date}), it must be less than or equal to it. ",
                'error')
        else:
            # data_list = List of tuples [(Category, Total routed, total-with-pdf), ...]
            data_list = DoiRegister.routed_in_period(from_date, to_date)
            grand_total = total_pdf = 0
            for _, total, num_pdf in data_list:
                grand_total += total
                total_pdf += num_pdf
            data_list.append(("GT", grand_total, total_pdf))

    return render_template(
        'reports/routed_in_period.html',
        title='Routed in period',
        from_date=from_date,
        to_date=to_date,
        data=data_list,
        map_category_to_desc={
            "J": "Journal article",
            "B": "Book",
            "C": "Conference output",
            "P": "Preprint",
            "R": "Report",
            "V": "Review",
            "L": "Letter",
            "O": "Other",
            "GT": "GRAND TOTAL"
        },
        earliest_date_dmy=earliest_date_dmy
    )

@blueprint.route('/adhoc_duplicate_submissions', methods=['GET'])
def adhoc_duplicate_submissions():
    """
    Report on duplicate submissions from publishers in defined period - either display on GUI or Download.

    :GET parameter from_date: String "YYYY-MM-DD" date
    :GET parameter to_date: String "YYYY-MM-DD" date
    :GET parameter download_csv: String [OPTIONAL] "yes" = Download CSV file

    :return: Either displays GUI or downloads CSV file
    """
    request_args = request.args
    from_date = request_args.get("from_date")
    to_date = request_args.get("to_date")
    data_list = None
    # If one or both of from_date & to_date are provided then report is generated
    if from_date or to_date:
        if not to_date:
            # 1 week after from_date
            to_date = (datetime.strptime(from_date, "%Y-%m-%d") + relativedelta(days=7)).strftime("%Y-%m-%d")
        elif not from_date:
            # 1 week before to_date
            from_date = (datetime.strptime(to_date, "%Y-%m-%d") - relativedelta(days=7)).strftime("%Y-%m-%d")

        if from_date > to_date:
            flash(f"The from-date ({from_date}) is later than the to-date ({to_date}), it must be less than or equal to it. ", 'error')
        else:
            display_on_screen = request_args.get("download_csv", "").lower() != "yes"
            download_filename = f"duplicate_submissions_{from_date}_to_{to_date}.csv"
            tmp_filepath = f"/tmp/{download_filename}"

            # If want to display on-screen or (want to download-csv & the expected file is missing), then generate the report
            if display_on_screen or not os.path.exists(tmp_filepath):
                # If displaying on screen then the data_list is returned AND temporary CSV report file is saved (in case
                # subsequent download of the CSV is wanted).  This approach is taken because the report query is relatively
                # expensive and can take seconds to run.

                # data_list: [(Dup-count, "Publisher", "DOI", "Deposit Dates", "Note IDs", "Metrics", "Target Repos"), ...]
                data_list = generate_duplicate_submissions_report(from_date, to_date, tmp_filepath, return_data=display_on_screen)

            # If download_csv is required
            if not display_on_screen:
                return send_from_directory("/tmp", download_filename, as_attachment=True)

    return render_template(
        'reports/duplicate_submissions.html',
        title='Publisher duplicate submissions',
        from_date=from_date,
        to_date=to_date,
        data=data_list,
        csv_link=url_for(".adhoc_duplicate_submissions", from_date=from_date, to_date=to_date, download_csv="yes")
    )


@blueprint.route('/misc_reports', methods=['GET'])
def misc_reports():
    # Dict that maps report keyword to tuple: (function-name, kwargs)
    report_funcs = {
        # "aff_analysis": (provider_aff_usage_report, {}),  - REPORT PRODUCED BY `scheduler.py` ##
        # "aff_org_analysis": (reports.provider_aff_org_report, {}),  - REPORT PRODUCED BY `scheduler.py` ##
        # "note_analysis": (note_types_report, {}),         - REPORT PRODUCED BY `scheduler.py` ##
        "matching_params": (matching_params_report, {"sep": "  ~  "}),
        "matching_params_nl": (matching_params_report, {"sep": "\n"}),
        "matching_params_json": (matching_params_json, {"indent": 4}),
    }
    misc_reports_form = MiscReportScriptsForm()
    if request.args:
        report_type = request.args.get("report_selector")
        if report_type:
            # The `report_info` tuple has following 5 elements:
            #   0 - Report summary (displayed as select field option)
            #   1 - Report description (added as title attribute to select field option)
            #   2 - Further information
            #   3 - Report name
            #   4 - Output filename for script (could contain '{}' placeholders if script can fill them)
            #   5 - Boolean flag indicates if report is run as a Batch (True) or Online (False) job
            rep_title, rep_desc, rep_info, rep_name, rep_filename, rep_batch_ind =\
                misc_reports_form.report_info.get(report_type, (None, None, None, None, None, None))
            # If a long running report - we need to trigger a job in the batch scheduler to run it
            if rep_batch_ind:
                send_to_email = current_user.get_email()
                # Trigger batch job to produce report
                Job.trigger_remote_job("REP",
                                       f"{current_app.config.get('SERVER_ID', 'Dev')}.Gui",
                                       "adhoc_report",
                                       func_args=[report_type, [send_to_email]]
                                       )
                msg = f"The report to <strong><i>{rep_title.lower()}</i></strong> has been scheduled to run as a background job.<br/><br/>It will be emailed to you upon completion at <i>{send_to_email}</i>."
                flash(msg, 'info+html')
            # will be an online report, as long as rep_title is not None
            elif rep_title:
                _misc_dir = MISC_DIR
                misc_dir = _report_directory(_misc_dir)
                if not os.path.exists(misc_dir):
                    os.makedirs(misc_dir)
                if "{" in rep_filename:
                    rep_filename = rep_filename.format(now_str("%Y-%m-%d"))
                file_path = os.path.join(misc_dir, rep_filename)
                try:
                    report_fn, kwargs = report_funcs.get(report_type)
                    metrics = MetricsRecord(server=current_app.config.get("SERVER_ID", "Dev"), proc_name="Adhoc-Report",
                                            measure="rec")
                    file_path, rec_count = report_fn(file_path, **kwargs)
                    duration_secs = metrics.log_and_save(log_msg=". Scanned {} record{}", count=rec_count,
                                                         extra={report_type: ""})
                    download_path = os.path.join(_misc_dir, os.path.basename(file_path))
                    mins_secs_str = str(timedelta(seconds=int(duration_secs)))[-5:]
                    msg = f"<i>{rep_title}</i> report completed in {mins_secs_str} - <a href=\"{url_for('.serve_report', path=download_path)}\">download report</a>."
                    flash(msg, 'info+html')
                except Exception as e:
                    msg = f"Failed to run report: '{report_type}'."
                    current_app.logger.error(msg, exc_info=True)
                    flash(f"{msg}<br>{repr(e)}", "error+html")
        # request args were passed (so page presumably already displayed), we want to redisplay the page
        # WITHOUT having those args appended to URL
        return redirect(request.path)

    # If no request args passed with URL (i.e. Submit button was NOT pressed) then display page
    return render_template(
        'reports/run_misc_reports.html',
        title='Run miscellaneous reports',
        report_form=misc_reports_form
    )

