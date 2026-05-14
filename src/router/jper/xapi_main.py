"""
xapi_main.py

Main module for deploying 'xapi' (Router API ONLY) service.  This module starts API application & mounts the
endpoints for 2 versions of API: v3 & v4.

Note that 'xapi' is used with 'xweb' service, which delivers Router Web GUI (with both running on separate App
servers), as an alternative to the orginal 'jper' service which combines both API & Web GUI on a single App server.
The 'jper' and 'xweb' service are both delivered by web_main.py module.

To start the 'xapi' application directly using the python web server, you can just do
::
    python xapi_main.py

IMPORTANT: Refer to documentation (in this repository) for more details how to deploy in Production / Staging / Test env.
"""
import os
from octopus.core import initialise, add_config_from_module
from router.jper.app import app
from router.jper.views.webapi import blueprint as webapi
# from sword2.server.views.blueprint import sword   # NOT currently supporting SWORD-IN


# Configuration to stop surplus whitespace being output by Jinja templates (used for emails, for example as result of
# publisher submission validation)
app.jinja_env.trim_blocks = True
app.jinja_env.lstrip_blocks = True

# In following 2 registrations, a default URL parameter named `api_vers` is defined with a value of "3" or "4"; when
# the `xapi_main` app receives a request with an API URL prefix, then the api_vers is assigned as if it was actually
# supplied in the URL. This value is then passed to the view function (in webapi.py).
app.register_blueprint(webapi, name="v4_api", url_prefix=app.config.get('API_URL_PREFIX'), url_defaults={'api_vers': app.config.get('API_VERSION')})
app.register_blueprint(webapi, name="v3_api", url_prefix=app.config.get('OLD_API_URL_PREFIX'), url_defaults={'api_vers': app.config.get('OLD_API_VERSION')})


def make_app():
    """
    :return: 'xapi' Router API app
    """
    with app.app_context():
        initialise()
        app.logger.info(f"Making 'xapi' app (PID: {os.getpid()}  Parent-PID: {os.getppid()})")
    return app


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config", help="additional configuration to load (e.g. for testing)")
    args = parser.parse_args()

    if args.config:
        add_config_from_module(app, args.config)

    make_app()

    app.run(host='0.0.0.0',
            port=app.config['PORT'],
            threaded=app.config.get("THREADED", False))
