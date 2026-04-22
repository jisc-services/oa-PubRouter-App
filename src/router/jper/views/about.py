'''
Created on 18 Nov 2015

Webpage - Graphic User Interface for About information

@author: Ruben Romartinez
'''

from flask import Blueprint, current_app, render_template
from flask_caching import Cache
from router.jper.app import app
from router.shared.models.account import AccOrg
from router.jper.models.admin import CmsHtml

SIX_HOURS = 21600  # cache time to live of 6 hours (21600 seconds)

# Create cache for app - some web pages are cached to repeat unnecessary database accesses for infrequently changing data
cache = Cache(app)

blueprint = Blueprint('about', __name__)

@blueprint.route('/')
def index():
    return render_template('about/about.html', title='About')


@blueprint.route('/institutions/', methods=['GET'])
def institutions():
    return render_template('about/institutions.html', title='Information for Institutions')


@blueprint.route('/publishers/', methods=['GET'])
def publishers():
    return render_template('about/publishers.html', title='Information for Publishers')


@blueprint.route('/resources/', methods=['GET'])
def resources():
    return render_template(
        'about/resources.html',
        title="Technical Information",
        docu_base_url=current_app.config.get("DOCU_BASE_URL", ""),
        docu_api_url=current_app.config.get("DOCU_API_URL", ""),
    )


@cache.cached(timeout=SIX_HOURS, key_prefix="pub_tbl_html")
def get_publishers_table_html_cached():
    # Retrieve live publisher details
    content_rec_list = CmsHtml.list_content_of_type("pub_provider", "L")  # Get Live content records
    # Format HTML of repeating <tr> rows for insertion into table (inside <tbody> element).
    tr_html_list = ["<tr><td>{pub}</td><td>{desc}</td></tr>".format(**cms_rec.get("fields", {}))
                    for cms_rec in content_rec_list]
    return "".join(tr_html_list)  # Concatenate <tr> rows into single block of HTML


@cache.cached(timeout=SIX_HOURS, key_prefix="harv_tbl_html")
def get_harvesters_table_html_cached():
    # Retrieve live harvester details
    content_rec_list = CmsHtml.list_content_of_type("harv_provider", "L")  # Get Live content records
    # Format HTML of repeating <tr> rows for insertion into table (inside <tbody> element).
    tr_html_list = ["<tr><td>{harv}</td><td>{desc}</td></tr>".format(**cms_rec.get("fields", {}))
                    for cms_rec in content_rec_list]
    return "".join(tr_html_list)  # Concatenate <tr> rows into single block of HTML


@blueprint.route('/providerlist/', methods=['GET'])
def providerlist():
    return render_template('about/providers.html',
                           title="List of Router Content Providers",
                           publisher_tr_html=get_publishers_table_html_cached(),
                           harvester_tr_html=get_harvesters_table_html_cached()
                           )


@blueprint.route("/start-up-guide-for-institutions/", methods=['GET'])
def startupguide():
    return render_template('about/startupguide.html', title="Start-up Guide For Institutions")


@cache.cached(timeout=SIX_HOURS, key_prefix="recipient_repos")
def get_recipient_repos_cached():
    ###
    #   Get Repositories list
    #   These are sorted in name/description alphabetical order
    ###
    last_updated = ''
    repositories = []
    # Retrieve ALL Not deleted And LIVE Repository accounts, that do not have a repository status of "off"
    for id, org_name, live_date in AccOrg.get_recent_active_live_org_names_sorted(acc_type="R"):
        repositories.append(org_name)
        # First record is most recent, so save live date
        if not last_updated:
            last_updated = live_date.strftime("%d-%b-%Y")
    # Sort repositories by name (desc)
    repositories.sort(key=str.upper)
    return last_updated, repositories


@blueprint.route('/recipientlist/', methods=['GET'])
def recipientlist():
    last_updated, repositories = get_recipient_repos_cached()
    return render_template('about/recipientlist.html',
                           title="List of Participating Institutions",
                           repositories=repositories,
                           last_updated=last_updated)
