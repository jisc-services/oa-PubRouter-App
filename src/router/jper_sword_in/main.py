"""
Main script which implements the SWORD-IN endpoint.

This supports submission of a single Zip package containing JATS XML and PDF files as a minimum, or alternatively
submission of at least 2 separate non-zip files (a JATS XML file and a PDF file).

Upon successful submission an Unrouted notifiation is generated.  If Publisher auto-testing is in progress, then the
submission will be tested (just as if it was submitted by FTP or the Router API).

"""
import os
from octopus.core import initialise
from sword2.server.views.blueprint import sword
from router.jper_sword_in.app import app
from router.jper.views.account import blueprint as account

app.register_blueprint(sword, url_prefix="/sword2")
app.register_blueprint(account, url_prefix="/account")      # Needed for pub_test email as a URL is created


def make_app():
    """
    When using gunicorn or the flask cli to run an app, need to call this function to initialise.

    :return: Sword_in app updated with web routes.
    """
    with app.app_context():
        initialise()
        app.logger.info(f"Making 'sword_in' app (PID: {os.getpid()}  Parent-PID: {os.getppid()})")
    return app


if __name__ == "__main__":
    make_app()
    app.run(host='0.0.0.0',
            port=app.config['PORT'],
            threaded=app.config.get("THREADED", False))
