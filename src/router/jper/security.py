"""
Flask security methods/classes to use when authenticating
"""
from flask import redirect, url_for, abort, make_response, jsonify, request, flash
from flask_login import current_user
from functools import wraps


def json_abort(status_code, error_message=None):
    """
    JSONified version of Flask's abort function.

    Will abort the request and return a JSON response with a set error message.

    @param status_code: Status code to return in the response
    @param error_message: Error message to add to the JSON response
    """
    # Allow it to be used just like the normal abort if you don't want to add a message
    if error_message is None:
        error_message = "There was a problem with your request"
    response = make_response(jsonify(error=error_message), status_code)
    abort(response)


# Just adds a simple way of reducing duplication of error messages
class ErrorMessages:
    # INVALID_API_KEY_ERROR = "A valid API key is required."
    FORBIDDEN_ERROR = "Your account does not have permission to perform this function."
    DEACTIVATED_ACCOUNT_ERROR = (
        "Your account is currently deactivated. "
        "Please contact XXXX@YYYY.ac.uk mentioning Publications Router for further information."
    )


def _redirect_anonymous():
    return redirect(url_for('account.login'))

## Decorators for use ONLY in GUI context (function names end with `__gui`) ##

def _gui_auth_n_param_injection(f, ok_func, *args, **kwargs):
    """
    Performs standard authentication, with parameter injection if OK, using `ok_func` to determine if user is authorised.

    ** `ok_func` must take 2 parameters: (curr_user, curr_org_ac)

    If a 'read-only' user & they attempt anything other than a GET request, a 403 unuathorised message will be returned.
    
    INJECTS `curr_user` & `cu_org_acc` kwarg parameter values into the function being wrapped.

    @param f: Function being "wrapped" by decorator
    @param ok_func: Function that returns None if user authorised, otherwise an Integer error code (e.g. 401 or 403).
    @param args:
    @param kwargs:
    @return: Function being wrapped, with `curr_user` & `cu_org_acc` kwarg parameter values set (injected).
    """
    def redirect_url():
        """
        Obtain URL to redirect the user to - this will be request.referrer URL if it exists or otherwise the user's
        own account page
        @return: String - URL
        """
        return request.referrer or url_for('account.user_account', org_uuid=curr_org_ac.uuid, user_uuid=curr_user.uuid)


    if current_user.is_anonymous:
        return _redirect_anonymous()
    curr_user = current_user.copy()     # Assign to local variable for efficiency as current_user is a proxy
    curr_org_ac = curr_user.acc_org
    ret_code = ok_func(curr_user, curr_org_ac)
    if ret_code:
        if ret_code == 403:
            flash(ErrorMessages.FORBIDDEN_ERROR, "error")
            return redirect(redirect_url())
        else:
            abort(ret_code)

    # Trying to POST (Add/Update) or DELETE etc. && user is READ-ONLY && NOT updating own account
    if (request.method != "GET" and curr_user.is_read_only and
            request.path != url_for('account.user_account', org_uuid=curr_org_ac.uuid, user_uuid=curr_user.uuid)):
        flash(ErrorMessages.FORBIDDEN_ERROR, "error")
        # Redirect to the originating web page
        return redirect(redirect_url())

    # Inject values into function being wrapped
    kwargs["curr_user"] = curr_user
    kwargs["cu_org_acc"] = curr_org_ac
    return f(*args, **kwargs)


def org_user_or_admin_org__gui(id_key="org_uuid"):
    """
    Decorator for use in GUI context  - where `current_user` is a User Account (AccUser).

    Allows for either the current-user being associated with the specified Org account uuid, or an Admin Org account.

    This decorator requires an argument that which should be a string of the name of the argument that refers
    to the relevant account's id.

    Will redirect all anonymous users to the login page.

    IMPORTANT: Injects curr_user and cu_org_acc into function that it wraps

    :param id_key: The name of the routing argument that is used to get the account id. Defaults to 'account_id'.
    """
    def _org_user_or_admin_org_gui(f):
        @wraps(f)
        def decorator(*args, **kwargs):
            def test_ok_fn(curr_user, curr_org_ac):
                return None if curr_org_ac.is_super or curr_org_ac.uuid == kwargs.get(id_key) else 403

            return _gui_auth_n_param_injection(f, test_ok_fn, *args, **kwargs)

        return decorator
    return _org_user_or_admin_org_gui


def admin_org_only__gui(f):
    """
    Decorator for use in GUI context - where `current_user` is a User Account (AccUser).
    Allows admin org account (i.e. NOT repo or pub account) only access to a page on PubRouter's GUI .

    Will redirect all anonymous users to the login page.
    For non-Admin users Aborts with a 401 (Unauthorised)

    IMPORTANT: Injects curr_user and cu_org_acc into function that it wraps
    """
    @wraps(f)
    def decorator(*args, **kwargs):
        def test_ok_fn(curr_user, curr_org_ac):
            return None if curr_org_ac.is_super else 403

        return _gui_auth_n_param_injection(f, test_ok_fn, *args, **kwargs)

    return decorator


def user_admin_or_admin_org__gui(f):
    """
    Decorator for use in GUI context - where `current_user` is a User Account (AccUser).

    Allows User Org-admin or (YOUR-ORG) Org Admin account, except Read-only users, access to a page on PubRouter's GUI.

    Will redirect all anonymous users to the login page.
    For non-Admin users Aborts with a 401 (Unauthorised)

    IMPORTANT: Injects curr_user and cu_org_acc into function that it wraps
    """

    @wraps(f)
    def decorator(*args, **kwargs):
        def test_ok_fn(curr_user, curr_org_ac):
            if curr_org_ac.is_super:
                if not curr_user.is_read_only:
                    return None
            elif curr_user.is_org_admin and curr_org_ac.uuid == kwargs.get("org_uuid"):
                return None
            return 403  # Forbidden

        return _gui_auth_n_param_injection(f, test_ok_fn, *args, **kwargs)
    return decorator


def own_user_acc_or_org_admin_or_admin_org__gui(f):
    """
    Decorator for use in GUI context  - where `current_user` is a User Account (AccUser).

    Allows for either the displayed page being associated with current user, or current-user being Org-Admin or
    Admin Org account.

    Will redirect all anonymous users to the login page.

    IMPORTANT: Injects curr_user and cu_org_acc into function that it wraps
    """
    @wraps(f)
    def decorator(*args, **kwargs):
        def test_ok_fn(curr_user, curr_org_ac):
            return None if (curr_org_ac.is_super or
                            (curr_org_ac.uuid == kwargs.get("org_uuid") and
                             (curr_user.is_org_admin or curr_user.uuid == kwargs.get("user_uuid")))) else 403

        return _gui_auth_n_param_injection(f, test_ok_fn, *args, **kwargs)

    return decorator


def org_user_or_admin_org_or_401__gui(f):
    """
    Decorator for use in GUI JSON API context  - where `current_user` is a User Account (AccUser).

    Allows for either the current-user being associated with the specified Org account uuid, or an Admin Org account.

    Read-Only users can only submit GET requests - e.g. Does NOT allow POST, PATCH, DELETE.

    Will redirect all anonymous users to the login page.

    IMPORTANT: Injects curr_user and cu_org_acc into function that it wraps
    """
    @wraps(f)
    def decorator(*args, **kwargs):
        if current_user.is_anonymous:
            abort(401)  # Unauthorised
        curr_user = current_user.copy()     # Assign to local variable for efficiency as current_user is a proxy
        curr_org_ac = curr_user.acc_org

        if (not (curr_org_ac.is_super or curr_org_ac.uuid == kwargs.get("org_uuid")) or
                (request.method != "GET" and curr_user.is_read_only)):
            json_abort(403, ErrorMessages.FORBIDDEN_ERROR)

        kwargs["curr_user"] = curr_user
        kwargs["cu_org_acc"] = curr_org_ac
        return f(*args, **kwargs)
    return decorator


def admin_org_only_or_401__gui(f):
    """
    Decorator for use in GUI context - where `current_user` is a User Account (AccUser).

    Allows  Admin Org (i.e. only YOUR-ORG users) access where the user is NOT Read-only (for JSON API requests in GUI context).

    For non-Admin users Aborts with a 401 (Unauthorised)

    NOTE: Unlike the other decorators above, this does *NOT* inject curr_user or cu_org_acc into function that it wraps.
    """
    @wraps(f)
    def decorator(*args, **kwargs):
        if current_user.is_anonymous:
            abort(401)
        if not current_user.acc_org.is_super or (request.method != "GET" and current_user.is_read_only):
            json_abort(403, ErrorMessages.FORBIDDEN_ERROR)  # forbidden

        return f(*args, **kwargs)
    return decorator


## Decorators for use ONLY in API context  (function names end with `__api`) ##
## IMPORTANT - in API context the `current_user` is ALWAYS an Organisation account object (AccOrg)

def publisher_or_admin_org__api(f):
    """
    Decorator for use in API context - NOTE: `current_user` is an Organisation Account (AccOrg).
    Allows publishers and admin accounts for API requests.

    Aborts with a 401 (Unauthorised) if:
        * The user is anonymous
        * The user is not a publisher or admin

    IMPORTANT: Injects pub_acc into function that it wraps
    """
    @wraps(f)
    def decorator(*args, **kwargs):
        if current_user.is_anonymous:
            abort(401)  # Unauthorised
        curr_org_ac = current_user.copy()   # Assign to local variable for efficiency as current_user is a proxy
        # Org-account Not admin AND not publisher
        if not (curr_org_ac.is_super or curr_org_ac.is_publisher):
            json_abort(403, ErrorMessages.FORBIDDEN_ERROR)  # forbidden
        kwargs["pub_acc"] = curr_org_ac
        return f(*args, **kwargs)
    return decorator


def active_publisher_or_admin_org__api(f):
    """
    Decorator for use in API context - NOTE: `current_user` is an Organisation Account (AccOrg).
    Allows publishers that are active, and Org admin accounts for API requests.

    Aborts with a 401 (Unauthorised) if:
        * The user is anonymous
    Aborts with a 403 (Forbidden) if:
        * The user is not a publisher or admin
        * The user is an inactive publisher.

    IMPORTANT: Injects pub_acc into function that it wraps
    """
    @wraps(f)
    def decorator(*args, **kwargs):
        if current_user.is_anonymous:
            abort(401)  # Unauthorised
        curr_org_ac = current_user.copy()   # Assign to local variable for efficiency as current_user is a proxy
        if not curr_org_ac.is_super:
            if not curr_org_ac.is_publisher:
                json_abort(403, ErrorMessages.FORBIDDEN_ERROR)  # Forbidden
            if curr_org_ac.publisher_data.is_deactivated():
                json_abort(403, ErrorMessages.DEACTIVATED_ACCOUNT_ERROR)  # Forbidden
        kwargs["pub_acc"] = curr_org_ac
        return f(*args, **kwargs)
    return decorator


def authentication_required__api(f):
    """
    Decorator for use in API context - NOTE: `current_user` is an Organisation Account (AccOrg).
    Allows any valid account for API requests.

    Aborts with a 401 (Unauthorised) if:
        * The user is anonymous
    """
    @wraps(f)
    def decorator(*args, **kwargs):
        if current_user.is_anonymous:
            abort(401)  # Unauthorised
        return f(*args, **kwargs)
    return decorator


