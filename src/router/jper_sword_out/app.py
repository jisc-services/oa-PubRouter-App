"""
Initial sword out app.

Adds config from config module to app.
"""
from flask_login import current_user
from octopus.lib.flask import create_flask_decorator
from octopus.core import create_app
# Load base configuration (used by all environments) and environment specific config
app = create_app(
    __name__,
    ["router.shared.global_config.base",
     "router.shared.global_config.{env}",
     "router.jper_sword_out.config.base",
     "router.jper_sword_out.config.{env}"],
    has_jinja_templates=True,
    has_login_manager=True
)
app_decorator = create_flask_decorator(app)


@app.login_manager.user_loader
def anonymous_user(_):
    """
    Provides a default user_loader callback for the Flask LoginManager.
    :param _: The user_id, which is ignored because the user is always anonymous.
    :return: The flask_login current_user.
    """
    return current_user
