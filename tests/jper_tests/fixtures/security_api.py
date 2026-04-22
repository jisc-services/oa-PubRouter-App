"""
Blueprint that has an endpoint for each security API decorator.

These are in different file from the security_gui endpoints so the `@blueprint.before_request` can be specified
to mimic the webapi view functions.
"""
from flask import Blueprint, jsonify, g
from router.jper import security

blueprint = Blueprint('security_api', __name__)

@blueprint.before_request
def before_req():
    # We create this attribute so that Flask's "user" account retrieval is handled differently for API requests compared
    # to other requests (such as GUI web app usage).
    # IMPORTANTLY, this results in an Organisation Account being retrieved into current_user, rather than a User Account.
    g.api_request = True


@blueprint.route("/publisher_or_admin_org__api")
@security.publisher_or_admin_org__api
def publisher_or_admin_org__api(**kwargs):
    return jsonify({}), 204


@blueprint.route("/active_publisher_or_admin_org__api")
@security.active_publisher_or_admin_org__api
def active_publisher_or_admin_org__api(**kwargs):
    return jsonify({}), 204


@blueprint.route("/authentication_required__api")
@security.authentication_required__api
def authentication_required__api(**kwargs):
    return jsonify({}), 204

