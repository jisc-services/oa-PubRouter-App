"""
web_main.py

Main module for deploying 'jper' (Router GUI Web + API) or 'xweb' (Router Web GUI ONLY) service.
This module starts the application & mounts the endpoints.  Mounting of the API v3 & v4 endpoints is conditional
on configuration value WEB_API_TYPE - which determines whether the module provides the 'jper' or 'xweb' service.

Note that if 'xweb' service is deployed, then 'xapi' service (see xapi_main.py) would normally be deployed on the
App2 server to provide Router API service.

To start the application directly using the python web server, you can just do
::
    python web_main.py

IMPORTANT: Refer to documentation (in this repository) for more details how to deploy in Production / Staging / Test env.
"""
import os
import binascii

from flask import render_template
from flask_caching import Cache
from octopus.lib.http_plus import http_get_xml_etree
from octopus.core import initialise, add_config_from_module
from octopus.lib.webapp import custom_static
from router.shared.models.account import AccOrg
from router.jper.models.admin import CmsHtml
from router.jper.app import app, app_decorator     # need to import app_decorator as other modules import it from here.
# from router.jper.cli import load_cli
from router.jper.views.about import blueprint as about
from router.jper.views.admin import blueprint as admin
from router.jper.views.account import blueprint as account
from router.jper.views.harvester import harvester
from router.jper.views.reports import blueprint as reports
# from router.jper.views.query import blueprint as query ### 9/10/2020 AR: Looks like this not needed
web_api_app = app.config.get("WEB_API_TYPE")
run_api = web_api_app == "jper" or app.config.get("TESTING") is True
if run_api:
    web_api_app = "jper"
    from router.jper.views.webapi import blueprint as webapi
from router.jper.views.website import blueprint as website

# from sword2.server.views.blueprint import sword   # NOT currently supporting SWORD-IN

# Configuration to stop surplus whitespace being output by Jinja templates
app.jinja_env.trim_blocks = True
app.jinja_env.lstrip_blocks = True

SIX_HOURS = 21600  # cache time to live of 6 hours (21600 seconds)

# Create cache for app
cache = Cache(app)


@cache.cached(timeout=SIX_HOURS, key_prefix="blog_post")
def get_blog_post_cached():
    """
    Get data from the pubrouter blog, and create a dict of the information for use in index.html
    Simply grabs the latest post off of the below url, and returns a dict containing information needed for an <a> tag.
    Also, returns blog URLs for current and old blog sites.

    :return: dict containing {title, url, blog_url, old_blog_url}
    """
    blog_url = app.config["BLOG_URL"]
    blog_feed_url = blog_url + "feed/"
    # Setting Accept-Encoding header to exclude the default "gzip" which causes problems
    headers = {"Accept-Encoding": "compress, deflate, br"}
    title = None
    url = None

    # Attempt to retrieve latest pubrouter blog post from ScholComms blog
    try:
        blog_xml_etree = http_get_xml_etree(blog_feed_url, headers=headers)
        first_item = blog_xml_etree.find(".//item")
        if first_item is not None:
            title = first_item.findtext("title")
            if title:
                # A URL only makes sense if a title exists
                url = first_item.findtext("link")
    except Exception as e:
        app.logger.warning(
            f"Couldn't get latest YOUR-ORG Scholcomms Router blog post from {blog_feed_url} with headers {headers} - {str(e)}")
        # Some http error to the scholarly communications blog - we will use default url below
        pass

    # Apply defaults for title and url if needed
    if not url:
        title = "Publications Router blog posts"
        url = blog_url

    return {"title": title, "url": url, "blog_url": blog_url, "old_url": app.config.get("OLD_BLOG_URL")}


@cache.cached(timeout=SIX_HOURS, key_prefix="repo_names")
def get_repo_org_names_cached():
    return [org_name for id, org_name, live_date
            in AccOrg.get_recent_active_live_org_names_sorted(acc_type="R", limit=3)]


@cache.cached(timeout=SIX_HOURS, key_prefix="pub_names")
def get_publisher_names_block_cached():
    """
    Retrieve publisher name block from CMS system (cms_html table)
    """
    # We expect to find a single live record
    content_rec_list = CmsHtml.list_content_of_type("3_pubs", "L")  # Get Live content record(s)
    if content_rec_list:
        return content_rec_list[0].get("fields", {}).get("pubs", "")
    else:
        return ""


@cache.cached(timeout=SIX_HOURS, key_prefix="info_box")
def get_info_box_cached():
    """
    Retrieve information blocks from CMS system (cms_html table)
    """
    # Retrieve live info_box records
    content_rec_list = CmsHtml.list_content_of_type("info_box", "L")  # Get Live content record(s)
    # Format HTML of repeating <tr> rows for insertion into table (inside <tbody> element).
    info_box_list = ["{info}".format(**cms_rec.get("fields", {})) for cms_rec in content_rec_list]
    if info_box_list:
        return f'<div class="span-11 box box--padding-medium box--brd-mgreyblue box--bg-lblue cms">{"".join(info_box_list)}</div><br>'
    else:
        return ""


@app.route("/")
def index():
    """
    Default index page

    :return: Flask response for rendered index page
    """
    return render_template("index.html",
                           information_block=get_info_box_cached(),
                           publiser_names_block=get_publisher_names_block_cached(),
                           repo_org_names=get_repo_org_names_cached(),
                           blog_post=get_blog_post_cached())


app.register_blueprint(admin, url_prefix="/admin")
app.register_blueprint(about, url_prefix="/about")
# adding account management, which enables the login functionality for the api
try:
    app.register_blueprint(account, url_prefix="/account")
except ValueError:
    # This occurs when running all pytests because it doesn't seem to flush imports between successive test files
    # and scheduler.py performs the same registration
    pass

app.register_blueprint(harvester, url_prefix="/harvester")
app.register_blueprint(reports, url_prefix="/reports")
# app.register_blueprint(query, url_prefix="/query")
# Add the SWORD2 API at SERVER_NAME/sword
# app.register_blueprint(sword, url_prefix="/sword")    # NOT currently supporting SWORD-IN
app.register_blueprint(website, url_prefix="/website")

if run_api:
    # In following 2 registrations, a default URL parameter named `api_vers` is defined with a value of "3" or "4"; when
    # the `web_main` app receives a request with an API URL prefix, then the api_vers is assigned as if it was actually
    # supplied in the URL. This value is then passed to the view function (in webapi.py).
    app.register_blueprint(webapi, name="v4_api", url_prefix=app.config.get('API_URL_PREFIX'), url_defaults={'api_vers': app.config.get('API_VERSION')})
    app.register_blueprint(webapi, name="v3_api", url_prefix=app.config.get('OLD_API_URL_PREFIX'), url_defaults={'api_vers': app.config.get('OLD_API_VERSION')})


if app.config.get("FUNCTIONAL_TEST_MODE", False):
    from router.jper.views.test import blueprint as test
    app.register_blueprint(test, url_prefix="/test")


# this allows us to override the standard static file handling with our own dynamic version
@app.route("/static/<path:filename>")
def static(filename):
    """
    Serve static content

    :param filename: static file path to be retrieved
    :return: static file content
    """
    return custom_static(filename)


# Make this global between all threads - doesn't matter if it gets overwritten while the other threads are starting
global STATIC_CACHE_HASH
STATIC_CACHE_HASH = binascii.hexlify(os.urandom(8))


@app.url_defaults
def static_cache_buster(endpoint, values):
    """
    If the endpoint is static, add the generated hash as a query parameter of the URL.

    ex: url_for("static", filename="js/something.js") becomes /static/js/something.js?hash={STATIC_CACHE_HASH}.

    :param endpoint: First argument of url_for (like 'static' or 'harvester.webservice')
    :param values: keyword arguments applied to url_for
    """
    if endpoint == "static":
        values["hash"] = STATIC_CACHE_HASH


# Load flask cli (command line interface) related code
# It must be loaded here as this is the file defined in the FLASK_APP environment variable - otherwise the shell
# processor will not be loaded.
# with app.app_context():
#     load_cli()


def make_app():
    """
    When using gunicorn or the flask cli to run an app, it doesn't import jper.web_main as main. This means it
    doesn't run initialise, and then in turn doesn't add the file logger to the instance, meaning that nothing is logged
    to jper.log. This function runs initialise so gunicorn and the flask cli can successfully use the logger.

    :return: JPER app updated with web routes.
    """
    with app.app_context():
        initialise()
        app.logger.info(f"Making '{web_api_app}' app (PID: {os.getpid()}  Parent-PID: {os.getppid()})")
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
            # debug=app.config['LOGLEVEL'] == 'DEBUG',      # Commented out as otherwise Pycharm Debugger fails to run
            threaded=app.config.get("THREADED", False))
