"""
Administration only endpoints.
"""
import json
import re
from csv import reader as csv_reader
from flask import Blueprint, render_template, request, flash, url_for, redirect, send_file, current_app, jsonify
from flask_login import current_user
from flask_caching import Cache
# from octopus.lib.scheduling import printable_schedule_list
from octopus.lib.csv_files import create_in_memory_csv_file
from octopus.lib.files import bytes_io_to_string_io
from router.jper.app import app
from router.shared import mysql_dao
from router.jper.forms.admin import IdentifierUploadForm, JsonRecordForm, MetricDisplayForm
from router.jper.models.identifier import Identifier
from router.jper.models.admin import CmsMgtCtl, CmsHtml
from router.shared.models.schedule import displayable_schedule_list_from_config, displayable_schedule_list_from_db, Job, PENDING, FINISHED
from router.shared.models.metrics import MetricsRecord
from router.jper.views.utility_funcs import get_page_details_from_request, calc_num_of_pages
from router.jper.security import admin_org_only__gui, json_abort, admin_org_only_or_401__gui

cache = Cache(app)

blueprint = Blueprint("admin", __name__)


def _flash_and_redirect(message, is_error=False):
    """
    Simple way of setting a flash and redirecting to the index page after a post request.

    :param message: message to flash
    :param is_error: Whether to set the error category for the flash or not

    :return: Redirect response object for admin.index
    """
    if is_error:
        flash(message, "error")
    else:
        flash(message, "info")
    return redirect(url_for("admin.index"))


@blueprint.route("/")
@admin_org_only__gui
def index(curr_user=None, cu_org_acc=None):
    """
    Simply add form and make the page.
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION

    """
    form = IdentifierUploadForm()
    return render_template("admin/index.html",
                           curr_user_acc=curr_user,
                           form=form,
                           title='Administration Panel')


@blueprint.route("/identifiers", methods=["GET", "POST"])
@admin_org_only_or_401__gui
def identifiers():
    """
    Process requests related to identifier administration.
    """
    def _post_identifiers():
        """
        Update the identifiers by a given type and csv file.

        The CSV file MUST have the following:
            At least two rows
            The first row MUST be the id values of the identifier.
            The second row MUST be the names corresponding to the ID (ex: University of JISC)
        """

        form = IdentifierUploadForm(request.form)
        file = request.files.get("csv_file")
        error = None
        if form.validate():
            if file:
                filename = file.filename
                if filename.endswith(".csv"):
                    string_data = bytes_io_to_string_io(file)
                    if string_data:
                        try:
                            csv_file = csv_reader(string_data)
                            num_loaded = Identifier.reload_type_by_identifier_iterable(csv_file, form.choices.data)
                        except Exception as e:
                            error = f"Problem processing CSV file which must contain rows with 'Institution name' & 'Numeric identifier' (in any order). {str(e)}."
                    else:
                        error = "File data was binary, expecting a csv text file."
                else:
                    error = "Filename must end in '.csv'"
            else:
                error = "No file was sent with the request"
        else:
            error = f"Given type was not a valid type {form.choices.data}"

        if error:
            response = _flash_and_redirect(error, True)
        else:
            response = _flash_and_redirect(f"Successfully uploaded {num_loaded} {form.choices.data} identifiers.")
        return response


    if request.method == "GET":
        row_count, bytes_io_obj = create_in_memory_csv_file(data_iterable=Identifier.identifiers_to_csv_list())
        return send_file(bytes_io_obj, mimetype='text/csv', download_name="identifiers.csv", as_attachment=True)
    else:
        return _post_identifiers()


@blueprint.route("/identifiers/<name>")
@admin_org_only_or_401__gui
def search_identifiers(name):
    """
    Endpoint that returns human readable data of identifiers

    :param name: String to fuzzy search over institutions with
    """
    type_ = request.args.get("type")
    data = [{"id": id.value, "institution": id.name, "type": id.type} for id in Identifier.search_by_name(name, type_)]
    return jsonify(data)


@blueprint.route("/json_rec", methods=["GET", "POST"])
@admin_org_only__gui
def json_rec(curr_user=None, cu_org_acc=None):
    """
    Process requests related to identifier administration.
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    """
    rec_obj = None
    json_data = ""
    if request.method == "GET":  # Display empty form
        dao_name = None
        rec_id = None
    else:  # POST - form submitted
        form_data = request.form
        action = form_data.get("action")  # action is either "pull" or "update"
        dao_name = form_data.get("dao_name")
        rec_id = form_data.get("rec_id").strip()
        # To support entry of multi-column keys - key parts can be separated by '|' or ',' with optional space(s) after
        rec_id_list = re.split(r'[|,] *', rec_id) if rec_id else []   # Avoid setting rec_id_list = [''] if rec_id is ''
        dao_class = getattr(mysql_dao, dao_name, None) if dao_name else None
        if len(rec_id_list) != len(dao_class.__pks__):
            str_a, str_b = ("s", " separated by comma or bar (|)") if len(dao_class.__pks__) > 1 else ("", "")
            flash(f"{dao_name} requires key{str_a} {dao_class.__pks__}{str_b}.",
                  "error")
        elif action == "pull":
            if dao_class and rec_id_list:
                rec_obj = dao_class.pull(*rec_id_list)
            if rec_obj is None:
                json_data = "** Record not found **"
                flash(f"Record with Id {rec_id_list} not found.", "info")
        elif not current_user.is_developer:  # Update
            flash(f"Only users with 'developer' role can update records.", "error")
        else:  # Update
            json_data = form_data.get("json_data")
            if dao_class and rec_id_list and json_data:
                try:
                    # convert string to dict
                    json_dict = json.loads(json_data)
                except Exception as e:
                    flash(f"JSON error: {str(e)}.", "error")
                else:  # JSON is OK
                    errors = [ f"{pk_col}: {rec_id_list[ix]}" for ix, pk_col in enumerate(dao_class.__pks__)
                               if rec_id_list[ix] != str(json_dict.get(pk_col))]
                    # Record ID's don't those in the record
                    if errors:
                        snippet = f"do not match those" if len(errors) > 1 else f"does not match that"
                        flash(f"You cannot change primary keys - Id values {errors} {snippet} in JSON record.", "error")
                    else:  # Supplied IDs matches IDs in JSON rec
                        # Put lock on original record (which we expect to exist)
                        latest_rec = dao_class.pull(*rec_id_list, for_update=True)
                        if latest_rec is None:
                            flash(f"Update failed - record with Id {rec_id_list} not found.", "error")
                        else:
                            try:
                                rec_obj = dao_class(json_dict)
                                # Updated date has changed
                                if latest_rec.updated != rec_obj.updated:
                                    rec_obj = latest_rec    # We want to display latest record
                                    raise Exception("Record has been updated by another process. Latest record is displayed.")
                                else:  # Updated date not changed (or there is no updated date - both return None)
                                    rec_obj.update(reload=True)
                                    flash("Record updated.", "success")
                            except Exception as e:
                                dao_class.cancel_transaction()  # Cancel transaction initiated by pull(…, for_update=True)
                                flash(f"Update failed - {str(e)}.", "error")

    return render_template(
        "admin/json_rec.html",
        curr_user_acc=curr_user,
        title="JSON record view/update",
        json_rec_form=JsonRecordForm(
            dao_name=dao_name,
            rec_id=rec_id,
            json_data=json.dumps(rec_obj.data, sort_keys=True, indent=2) if rec_obj else json_data
            )
        )

@blueprint.route("/version_info", methods=["GET"])
@admin_org_only__gui
def version_info(curr_user=None, cu_org_acc=None):
    """
    Display Router library version information.
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    """
    from importlib.metadata import distributions, version

    # Get list of library module names & versions, sorted by name (lower-case)
    lib_name_version_tuple_list = sorted([(d.name, d.version) for d in distributions()], key=lambda x: x[0].lower())
    jisc_module_tuple_list = [
        ("Router", version("router")),
        ("Octopus", version("octopus")),
        ("Sword2", version("python-sword2")),
    ]
    return render_template(
        "admin/version_info.html",
        title="Router version information",
        jisc_module_tuple_list=jisc_module_tuple_list,
        lib_name_version_tuple_list=lib_name_version_tuple_list,
        )

@blueprint.route("/manage_content", methods=["GET", "POST"])
@admin_org_only__gui
def manage_content(curr_user=None, cu_org_acc=None):
    """
    Add/change displayed webpage content
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    """
    return render_template(
        "admin/content_mgt.html",
        curr_user_acc=curr_user,
        title="Manage content"
        )


@blueprint.route("/content_ajax", methods=["GET", "POST"])
@admin_org_only_or_401__gui
def content_ajax():
    """
    Endpoint that handles Content Management AJAX queries from front end, possible functions:
    list_cms_types, list_content, update_content, insert_content, delete_content.

    *** WARNING *** - This function currently allows the input of potentially dangerous HTML or Javascript [JS] code
                   via the functions: _insert_content and _update_content.
                   This has been regarded as acceptable because it is only used by GUI screens available
                   to a limited number of trustworthy YOUR-ORG administrators.  This defect could be addressed by introducing
                   an HTML/JS checking/filtering function (which, importantly, allows some HTML) in a (new)
                   _validate_content function which is called before storing entered data in the database.


    JSON data structure varies depending on query being handled.

    list_cms_types:
    {
    'func': 'list_cms_types'
    }

    list_content:
    {
    'func': 'list_content',
    'ctype': '...reqd_cms_type...',
    }

    update_content, insert_content, delete_content:
    {
    'func': 'update_content' or 'insert_content' or 'delete_content',
    'id': '...record id...' **,
    'ctype': '...content-type...',
    'sort_value': '...sort-value...'**,
    'content': [...content...] **  // ??? should this be a list?
    }
    ** - May be absent
    """

    def _list_cms_types(json_dict):
        """
        Retrieve list of content-types (for e.g. for populating dropdown list)

        :param json_dict: dict - not used

        :return: List of lists
        """
        return CmsMgtCtl.list_cms_types()


    def _get_content_ctl(json_dict):
        """
        Retrieve content control record for particular cms_type.

        :param json_dict: dict - must contain 'cms_type'

        :return: Content control record dict
        """
        # If no record found for specified cms_type then raise an exception
        return CmsMgtCtl.pull(json_dict.get("cms_type"), wrap=False, raise_if_none=True)

    def _list_content(json_dict):
        """
        Retrieve content records of particular content type.

        :param json_dict: dict - must contain 'cms_type', and required 'status' values

        :return: List of record dicts
        """
        return CmsHtml.list_content_of_type(json_dict.get("cms_type"), json_dict.get("status"))

    def validate_json_dict(json_dict):
        # Check for mandatory fields
        errors = []
        for k in ("cms_type", "status"):
            if not json_dict.get(k):
                errors.append(k)
        if errors:
            raise Exception(" and ".join(errors) + (" field is" if len(errors) == 1 else " fields are") + " required")

        # Remove any non-data items elements
        for k in ("func"):
            json_dict.pop(k, None)
        return json_dict

    def _insert_content(json_dict):
        """
        Save content in the cms_html table.

        :param json_dict: Dict of record data to save as JSON, looks like:
            {
            "cms_type": "content type (FK to cms_ctl record)",
            "status": "CHAR(1) - one of "N" new, "L" live, "D" deleted, "S" superseded",
            "fields": {
                        "sort_value": "sort value",
                        "...": "CMS content value"
                      }
            }
        :return dict: Success info
        """
        validate_json_dict(json_dict)
        CmsHtml(json_dict).insert()
        return {"msg": "Content saved"}

    def _update_content(json_dict):
        """
        Update the specified content record - this involves saving original as superseded & then saving changes as
        a new record.

        :param json_dict: dict that must contain "id" element
            {
            "cms_type": "content type (FK to cms_ctl record)",
            "id": <record id>,
            "status": "CHAR(1) - one of "N" new, "L" live, "D" deleted, "S" superseded",
            "fields": {
                        "sort_value": "sort value",
                        "...": "CMS content value"
                      }
            }

        :return: Dict
        """
        validate_json_dict(json_dict)
        result_str = CmsHtml.save_and_archive_content(json_dict)
        return {"msg": f"Record {result_str}"}

    def _update_status(json_dict):
        """
        Change status of record

        :param json_dict: dict that must contain "id" & "status" elements

        :return: Dict
        """
        validate_json_dict(json_dict)
        result_str = CmsHtml.update_status(json_dict)
        return {"msg": f"Record {result_str}"}

    def _clear_cache(ignore):
        """
        Clear router's cached
        """
        cache.clear()
        return {"msg": "Cache has been cleared"}


    func_lookup = {
        "list_cms_types": _list_cms_types,
        "get_content_ctl": _get_content_ctl,
        "list_content": _list_content,
        "update_content": _update_content,
        "insert_content": _insert_content,
        "update_status": _update_status,
        "clear_cache": _clear_cache
    }

    data_dict = request.json if request.method == "POST" else request.values
    func_name = data_dict.get("func")
    func = func_lookup.get(func_name)
    if func:
        try:
            result = func(data_dict)  # Execute required function
            return jsonify(result)  # Send response to AJAX request
        except Exception as e:
            err_str = str(e)
            current_app.logger.error(f"In content_ajax - Function '{func_name}' failed with error: {repr(e)}")
    else:
        err_str = f"Function '{func_name}' missing or not recognised"


    # If we get this far then an error has occurred
    json_abort(400, err_str)


@blueprint.route("/metrics")
@admin_org_only__gui
def metrics(curr_user=None, cu_org_acc=None):
    """
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    """
    request_args = request.args
    page_num, page_size = get_page_details_from_request(request_args)
    form_metrics = MetricDisplayForm(data=request_args)
    # If from-date set, but not to-date
    if form_metrics.from_date.data:
        if not form_metrics.to_date.data:
            form_metrics.to_date.data = "2050-01-01"
    elif form_metrics.to_date.data:
        form_metrics.from_date.data = "2020-01-01"

    recs_list, total_recs = MetricsRecord.list_metrics(
        page_num - 1,
        page_size,
        min_count=form_metrics.min_count.data,
        from_date=form_metrics.from_date.data,
        to_date=form_metrics.to_date.data,
        proc_name=form_metrics.proc_name.data
    )
    num_of_pages = calc_num_of_pages(page_size, total_recs) if total_recs is not None else None
    return render_template(
        "admin/metrics.html",
        curr_user_acc=curr_user,
        title="Router system metrics",
        recs_list=recs_list,
        num_of_pages=num_of_pages,
        page_num=page_num,
        form_metrics=form_metrics
    )


@blueprint.route("/schedule", methods=['GET', 'POST'])
@admin_org_only__gui
def schedule(curr_user=None, cu_org_acc=None):
    """
    Display the current schedule
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    """
    if request.method == "POST":
        err = None
        if current_user.is_developer:
            post_data = request.json
            rec_id = post_data.get("rec_id")
            func_name = post_data.get("func_name")
            if rec_id and func_name:
                try:
                    rec_id = int(rec_id)
                    job = Job.pull(rec_id, for_update=True, raise_if_none=True)
                    if job.status in (None, PENDING, FINISHED):
                        job.trigger_it()
                        flash(f"Job '<strong>{func_name}</strong>' (ID {rec_id}) has been triggered.", 'info+html')
                except Exception as e:
                    err = f"Triggering job '{func_name}' (ID {rec_id}) failed - Error: {repr(e)}"
            else:
                err = "Job `rec_id` and/or `func_name` not provided"
        else:
            err = "Triggering a job is restricted to developers"
        if err:
            flash(err, 'error')
            current_app.logger.error(err)
            return json_abort(400,  err)
        else:
            return {}   # Successful result - web page will automatically reload

    ## GET ##
    request_args = request.args
    mode = request_args.get("mode")
    show_active = mode != "config"  # Not show-config
    auto_reload = mode == "active_auto"
    sort_priority = request_args.get("sort") == "priority"
    full_date = request_args.get("full", "0") == "1"
    all_cols = show_active and request_args.get("cols") == "all"
    show_run_btns = show_active and current_user.is_developer
    info_msg = ""
    _config = current_app.config
    if show_active:
        schedule_list = displayable_schedule_list_from_db(sort_priority=sort_priority, full_date=full_date)
        if not schedule_list:
            info_msg = "There are no scheduled jobs in the database - this indicates that no batch services are currently running."
    else:
        schedule_list = displayable_schedule_list_from_config(
            _config.get("SCHEDULER_SPEC", []),
            _config.get("SCHEDULER_CONFLICTS", {}),
            full_date=full_date
        )

    return render_template(
        "admin/schedule.html",
        curr_user_acc=curr_user,
        title=f"Router {'active' if show_active else 'configured'} batch job schedule",
        show_active=show_active,
        auto_reload=auto_reload,
        sort_priority=sort_priority,
        full_date=full_date,
        all_cols=all_cols,
        show_run_btns=show_run_btns,
        schedule_list=schedule_list,
        info=info_msg,
        refresh=_config.get("SCHEDULER_SLEEP", 5)
    )
