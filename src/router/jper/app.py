"""
Initial app for JPER.

Loads config and adds initialise module to octopus functions.

Also defines functions used by Flask Login Manager.
"""
from flask import request, g
from flask.sessions import SecureCookieSessionInterface
from octopus.lib.flask import create_flask_decorator
from octopus.core import create_app
from router.shared.models.account import AccOrg, AccUser


class CustomAPISessionInterface(SecureCookieSessionInterface):
    """Prevent creating session from API requests."""
    def save_session(self, *args, **kwargs):
        if g.get('api_request'):
            return
        return super(CustomAPISessionInterface, self).save_session(*args, **kwargs)


# Load base configuration (used by all environments), followed by environment specific config
# Need to load harvester config, because of harvester GUI functionality
app = create_app(__name__,
                 ["router.shared.global_config.base",
                  "router.shared.global_config.{env}",
                  "router.harvester.config.base",
                  "router.harvester.config.{env}",
                  "router.jper.config.base",
                  "router.jper.config.{env}"],
                 has_jinja_templates=True,
                 has_login_manager=True)
# update_init(app, 'jper.initialise')   # No longer needed - but retained in case needed in future.

app.session_interface = CustomAPISessionInterface()

# Flask wrapper with initialised config for JPER.
app_decorator = create_flask_decorator(app)


def _get_apikey_from_request():
    request_vals = request.values
    # Attempt to get from request params (we prefer lower case)
    api_key = request_vals.get("api_key")
    if not api_key:
        api_key = request_vals.get("API_KEY")
    return api_key


def get_org_acc_from_request():
    """
    Function to get an Organisation Account via API key.

    This function is used by Flask-login to authenticate a user via an API key sent in an API request.

    DOCS: https://flask-login.readthedocs.io/en/latest/#custom-login-using-request-loader

    :return: Org Account matching given api key, otherwise None.
    """
    api_key = _get_apikey_from_request()
    return AccOrg.pull_by_api_key(api_key) if api_key else None


@app.login_manager.user_loader
def get_user_acc_4_login_manager(userid):
    """
    Load EITHER an Organisation Account (if webapi request) OR a User account on behalf of the login manager depending
    on whether in API or GUI context.

    NOTE: The solution for api endpoints effectively gets the user from the request if available and ignores the
        user's session. This is due to how Flask-Login will ONLY attempt to load from the session if a session exists.

        If this function returns None Flask will attempt to also load the user from the request.

    :param userid: ID value (this is primary key ID, not UUID)
    :return: Either an Organisation or User account object, depending on whether API Request or not
    """
    try:
        org_or_user_ac = get_org_acc_from_request() if g.get("api_request") else AccUser.pull_user_n_org_ac(userid, "user_id")
    except Exception as e:
        org_or_user_ac = None
        app.logger.critical("Failed to load account (for login manager). " + repr(e))

    return org_or_user_ac


@app.login_manager.request_loader
def get_user_from_request_4_login_manager(*args, **kwargs):
    """
    IMPORTANT - returns EITHER an Organisation Account OR a User Account depending on whether Request is in API context
    or NOT.
    """
    # Get the Organisation Account
    org_acc = get_org_acc_from_request()
    if org_acc is None:
        return None

    if g.get("api_request"):
        # Working in "API context"
        return org_acc
    else:
        # Working in "GUI context"
        # Create dummy API user
        user_acc = AccUser(
            {
            "id": 0,
            "created": org_acc.created,
            "last_success": None,
            "last_failed": None,
            "uuid": org_acc.uuid,
            "acc_id": org_acc.id,
            "username": "API-Key-user",
            "user_email": None,
            "surname": "API User",
            "forename": "The",
            "org_role": None,
            "role_code": "K",
            "password": None,
            "failed_login_count": 0
            }
        )
        user_acc.acc_org = org_acc
        return user_acc
