"""
Initial sword in app.

Adds config from config module to app.
"""
from flask.sessions import SecureCookieSessionInterface
from flask_login import current_user
from octopus.lib.flask import create_flask_decorator
from octopus.core import create_app


class CustomAPISessionInterface(SecureCookieSessionInterface):
    """Prevent creating session from SWORD-IN requests."""
    def save_session(self, *args, **kwargs):
        return

# Load base configuration (used by all environments) and environment specific config
app = create_app(
    __name__,
    [
        "router.shared.global_config.base",
        "router.shared.global_config.{env}",
        "router.jper.config.base",      # Some entries will be overwritten by those in jper_sword_in.config.base
        "router.jper.config.{env}",     # Some entries may be overwritten by those in jper_sword_in.config.{env}
        "router.jper_sword_in.config.base",
        "router.jper_sword_in.config.{env}"
    ],
    has_jinja_templates=True,
    has_login_manager=True
)
app.session_interface = CustomAPISessionInterface()

app_decorator = create_flask_decorator(app)


@app.login_manager.user_loader
def anonymous_user(_):
    """
    Provides a default user_loader callback for the Flask LoginManager.
    :param _: The user_id, which is ignored because the user is always anonymous.
    :return: The flask_login current_user.
    """
    return current_user
