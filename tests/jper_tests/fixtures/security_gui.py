"""
Blueprint that has an endpoint for each security GUI decorator.
"""
from flask import Blueprint, jsonify
from router.jper import security

blueprint = Blueprint('security_gui', __name__)


def _make_ret_dict(**kwargs):
    curr_user = kwargs.get("curr_user")
    cu_org_acc = kwargs.get("cu_org_acc")
    ret_dict = {}
    if curr_user:
        ret_dict.update({
            "u_id": curr_user.id,
            "u_username": curr_user.username,
            "u_uuid": curr_user.uuid
        })
    if cu_org_acc:
        ret_dict.update({
            "o_id": cu_org_acc.id,
            "o_orgname": cu_org_acc.org_name,
            "o_uuid": cu_org_acc.uuid,
        })
    return ret_dict


@blueprint.route("/admin_org_only__gui")
@security.admin_org_only__gui
def admin_org_only__gui(**kwargs):
    return jsonify(_make_ret_dict(**kwargs)), 200


@blueprint.route("/admin_org_only_or_401__gui")
@security.admin_org_only_or_401__gui
def admin_org_only_or_401__gui(**kwargs):
    return jsonify(_make_ret_dict(**kwargs)), 200


@blueprint.route("/org_user_or_admin_org__gui/<org_uuid>")
@security.org_user_or_admin_org__gui()
def org_user_or_admin_org__gui(org_uuid, curr_user=None, cu_org_acc=None):
    return jsonify(_make_ret_dict(curr_user=curr_user, cu_org_acc=cu_org_acc)), 200


@blueprint.route("/user_admin_or_admin_org__gui/<org_uuid>/<user_uuid>")
@security.user_admin_or_admin_org__gui
def user_admin_or_admin_org__gui(org_uuid, user_uuid, curr_user=None, cu_org_acc=None):
    return jsonify(_make_ret_dict(curr_user=curr_user, cu_org_acc=cu_org_acc)), 200


@blueprint.route("/own_user_acc_or_org_admin_or_admin_org__gui/<org_uuid>/<user_uuid>", methods=['GET', 'POST'])
@security.own_user_acc_or_org_admin_or_admin_org__gui
def own_user_acc_or_org_admin_or_admin_org__gui(org_uuid, user_uuid, curr_user=None, cu_org_acc=None):
    return jsonify(_make_ret_dict(curr_user=curr_user, cu_org_acc=cu_org_acc)), 200


@blueprint.route("/org_user_or_admin_org_or_401__gui/<org_uuid>", methods=['GET', 'POST'])
@security.org_user_or_admin_org_or_401__gui
def org_user_or_admin_org_or_401__gui(org_uuid, curr_user=None, cu_org_acc=None):
    return jsonify(_make_ret_dict(curr_user=curr_user, cu_org_acc=cu_org_acc)), 200
