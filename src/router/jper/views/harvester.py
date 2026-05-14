"""
Created on 18 Nov 2015

Webpage - Graphic User Interface for an harvester

@author: Mateusz.Kasiuba
"""
from flask import (Blueprint, request, flash, redirect, current_app, url_for, render_template, abort, make_response,
                   jsonify)
from octopus.lib.dates import now_str
from octopus.modules.mysql.dao import DAOException
from router.shared.models.account import AccOrg
from router.shared.models.harvester import HarvesterWebserviceModel, HarvErrorsModel, HarvHistoryModel
from router.jper.views.utility_funcs import get_page_details_from_request
from router.jper.forms.harvester import WebserviceForm, ServiceUsageForm
from router.jper.security import admin_org_only__gui, admin_org_only_or_401__gui, json_abort

harvester = Blueprint('harvester', __name__)

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


@harvester.route('/webservice/', methods=['GET', 'POST'])
@admin_org_only__gui
def webservice(curr_user=None, cu_org_acc=None):
    """
    List of webservices
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    """
    return render_template('harvester/webservice.html',
                           curr_user_acc=curr_user,
                           title='Harvester Sources',
                           webservice_list=HarvesterWebserviceModel.get_webservices_dicts())


@harvester.route('/history/', methods=['GET', 'POST'])
@admin_org_only__gui
def history(curr_user=None, cu_org_acc=None):
    """
    Page with list history queries form harvester
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    """
    page_num, page_size = get_page_details_from_request(request.args)
    history, num_of_pages = HarvHistoryModel.get_history(page_num - 1, page_size)
    return render_template('harvester/history.html',
                           curr_user_acc=curr_user,
                           title='Harvester History',
                           history_list=history,
                           num_of_pages=num_of_pages,
                           page_num=page_num)


@harvester.route('/history/<history_id>/errors', methods=['GET'])
@admin_org_only__gui
def history_errors(history_id, curr_user=None, cu_org_acc=None):
    """
    Page with list of errors for a particular history event
    :param history_id: Int - ID of harvester Run record
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    """
    if not history_id.isnumeric():
        _abort(400, "A numeric history record ID must be provided.")

    run_rec = HarvHistoryModel.get_hist_rec(history_id)
    if run_rec is None:
        _abort(404, "History record not found.")
    page_num, page_size = get_page_details_from_request(request.args)
    error_list, num_of_pages = HarvErrorsModel.get_error_list(page_num - 1, page_size, for_run_id=history_id)
    return render_template('harvester/error_list.html',
                           curr_user_acc=curr_user,
                           title='Harvester Errors',
                           run_details=run_rec,
                           error_list=error_list,
                           num_of_pages=num_of_pages,
                           page_num=page_num)


@harvester.route('/error/', methods=['GET'])
@admin_org_only__gui
def error(curr_user=None, cu_org_acc=None):
    """
    Page with error list form harvester
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    """
    page_num, page_size = get_page_details_from_request(request.args)
    error_list, num_of_pages = HarvErrorsModel.get_error_list(page_num - 1, page_size)
    return render_template('harvester/error_list.html',
                           curr_user_acc=curr_user,
                           title='Harvester Errors',
                           h1_extra=None,
                           run_details=None,
                           error_list=error_list,
                           num_of_pages=num_of_pages,
                           page_num=page_num)


@harvester.route('/manage/', defaults={'webservice_id': 0}, methods=['GET', 'POST'])
@harvester.route('/manage/<webservice_id>', methods=['GET', 'POST'])
@admin_org_only__gui
def manage(webservice_id, curr_user=None, cu_org_acc=None):
    """
    Manage page for a harvester webservice

    :param webservice_id: ID of the webservice to manage
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    """
    name = 'Edit harvester' if webservice_id else 'Add harvester'

    # Get, but not adding a new webservice
    if request.method == 'GET':
        if webservice_id:
            try:
                webservice = HarvesterWebserviceModel.get_webservice(webservice_id)
            except Exception as e:
                _abort(404, str(e))
        else:
            webservice = HarvesterWebserviceModel({})
        form = WebserviceForm(data=webservice.data)
    else: # POST
        form = WebserviceForm(request.form)
        if form.validate():
            try:
                webservice = HarvesterWebserviceModel(form.data)
                # Adding new webservice
                if webservice_id == 0:
                    webservice.insert()
                    webservice_id = webservice.id
                    # Deselect this NEW webservice for all Repositories (to stop them harvesting from it by default)
                    AccOrg.select_or_deselect_provider_from_all_repos(webservice_id, select=False)
                else:
                    webservice.id = webservice_id  # The form.data did not include the ID because the field is disabled
                    # Save modified webservice
                    webservice.update()
            except DAOException as e:
                flash(f'There was a problem saving the record: {str(e)}', 'error')
            else:
                flash('Record saved.', 'success')
            return redirect(url_for("harvester.manage", webservice_id=webservice_id))
        else:
            form.id.data = webservice_id  # The form.data did not include the ID because that field is disabled
            flash("Submission errors", "error")

    # This is the "Select or deselect ...." form on the manage page
    select_form = ServiceUsageForm(
        data={'total_repos': AccOrg.num_repositories(),
              'num_using': AccOrg.num_repositories_using_provider(webservice_id) if webservice_id else 0}
    )
    return render_template('harvester/manage.html',
                           curr_user_acc=curr_user, form=form, title=name, select_form=select_form)


@harvester.route('/manage/<webservice_id>/select', methods=['POST'])
@admin_org_only__gui
def select_or_not(webservice_id, curr_user=None, cu_org_acc=None):
    """
    For all repository accounts, set or unset webservice as used (i.e. the Used? checkbox is selected or deselected).

    :param webservice_id: Id of webservice to select
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    :return: redirects to the manage webservice page
    """
    select = "select" == request.form.get('action')
    try:
        webservice = HarvesterWebserviceModel.get_webservice(webservice_id)
        count = AccOrg.select_or_deselect_provider_from_all_repos(webservice_id,
                                                                   select=select,
                                                                   provider_name=webservice.data['name'])
        flash("Harvester {} for all repositories ({} records changed - see log for details).".format(
            "selected" if select else "deselected", count), 'success')
    except Exception as e:
        flash(f"str(e)", 'error')

    return redirect(url_for("harvester.manage", webservice_id=webservice_id))


@harvester.route('/golive/<webservice_id>', methods=['POST'])
@admin_org_only__gui
def golive(webservice_id, curr_user=None, cu_org_acc=None):
    """
    Make chosen webservice live
    :param webservice_id: Id of webservice to select
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    """
    # Retrieve harvester record we are about to make live
    try:
        webservice = HarvesterWebserviceModel.get_webservice(webservice_id, for_update=True)
        webservice.data["live_date"] = now_str("%Y-%m-%d")
        webservice.update()
    except DAOException as e:
        flash('There was a problem saving the record: {}'.format(str(e)), 'error')
    except ValueError as e:
        flash(str(e), 'error')
    else:
        flash('Harvester made Live.', 'success')
    return redirect(url_for("harvester.manage", webservice_id=webservice_id))


@harvester.route('/delete/<webservice_id>', methods=['GET', 'POST'])
@admin_org_only__gui
def delete(webservice_id, curr_user=None, cu_org_acc=None):
    """
    Delete chosen webservice
    :param webservice_id: Id of webservice to select
    :param curr_user: Current user - SET BY DECORATOR FUNCTION
    :param cu_org_acc: Current user's Organisation account - SET BY DECORATOR FUNCTION
    """
    try:
        # Delete the harvester webservice record and temporary harvester index (dict of webservice just deleted is returned)
        webservice = HarvesterWebserviceModel.delete_webservice_rec_and_index(webservice_id)

        current_app.logger.info(f"Deleted harvester webservice record: {str(webservice)}")

        # Remove reference to the deleted webservice from all Repositories that reference it in excluded_provider_ids list
        # (Passing select=True results in entries being deleted)
        AccOrg.select_or_deselect_provider_from_all_repos(webservice_id, select=True)

        flash('Record deleted.', 'success')
    except Exception as e:
        flash(f"Deletion failed - {str(e)}", 'error')
    # Return use to the harvester webservice list page
    return redirect(url_for("harvester.webservice"))


@harvester.route('/activate/<webservice_id>', methods=['GET', 'POST'])
@admin_org_only_or_401__gui
def activate(webservice_id):
    """
    Activate/deactivate the chosen webservice (of the webservice_id) 
    :param webservice_id: Id of webservice to select
    """
    try:
        # toggle the service activation status
        new_status = HarvesterWebserviceModel.toggle_status(webservice_id)
    except Exception as e:
        json_abort(400, str(e))  # forbidden
    return jsonify({"status": new_status})

