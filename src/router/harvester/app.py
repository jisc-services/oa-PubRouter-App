"""
Initial harvester app.

Adds config from config module to app.
"""
from octopus.lib.flask import create_flask_decorator
from octopus.core import create_app
# Load base configuration (used by all environments) and environment specific config
app = create_app(
    __name__,
    ["router.shared.global_config.base",
     "router.shared.global_config.{env}",
     "router.harvester.config.base",
     "router.harvester.config.{env}"],
    has_jinja_templates=True    # Critical error emails use jinja template
)
app_decorator = create_flask_decorator(app)

