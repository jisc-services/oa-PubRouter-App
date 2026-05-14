"""
All of the front end tests which do not use JavaScript. It is difficult/impossible to test JavaScript using
tests of this nature, all JavaScript tests are instead included in the robot tests.

Contains one base test class, TestFrontEnd, which contains all setup and teardown, also all helper functions currently
involved.

Contains 9 additional test suite classes, of which the first four are split up based on the
permissions of the users that the tests pertain to. Namely:

- TestFrontEndAnyone which includes tests which pertain to any user regardless of permissions.
- TestFrontEndRepositories, which only pertain to repository users.
- TestFrontEndPublishers, which only pertain to publisher users.
- TestFrontEndAdmin, which only pertain to administrator users.

The remaining  classes are for checking the <title> is rendered correctly by the views,
which were added as part of a drive to improve the accessibility of the web site. Each class
contains tests for views in a particular module. These are:

- TestIndexPageTitle - top level (web.py)
- TestAboutViewPageTitles - views.about
- TestAdminViewPageTitles - views.admin
- TestHarvesterViewPageTitles - views.harvester
- TestReportsViewPageTitles - views.reports
"""
import os
import csv
import requests
import warnings
import json
from collections import OrderedDict
from time import sleep
from functools import partial
from flask import url_for
from flask_caching import Cache
from io import StringIO
from unittest.mock import patch, Mock

from octopus.lib.data import strip_bad_text
from octopus.lib.files import AlwaysBytesIO
from octopus.lib.flask import response_to_html
from router.shared.models.note import RoutedNotification
from router.shared.models.account import AccOrg, AccRepoMatchParams, AccUser, OFF, OKAY, FAILING, PROBLEM
from router.jper.models.identifier import Identifier
from tests.fixtures.factory import AccountFactory, NotificationFactory, SwordFactory, FAILED, DEPOSITED
from tests.jper_tests.fixtures.models import IdentifierFactory
from tests.jper_tests.fixtures.testcase import JPERTestCase
from tests.harvester_tests.fixtures.harvester_utils import HarvesterTestUtils
from router.jper.web_main import app, app_decorator

cache = Cache(app)


class TestFrontEnd(JPERTestCase):
    # contains all set up and helper functions for all other test classes, acts as a base class to be inherited
    # for all other test classes

    @classmethod
    def setUpClass(cls):
         # List the tables (by table name) needed for testing
         cls.tables_for_testing = [
            'account', 'acc_user', 'cms_ctl', 'cms_html', 'acc_repo_match_params', 'h_webservice', 'h_errors',
            'h_history', 'acc_repo_match_params_archived', 'notification', 'notification_account', 'match_provenance',
            'pub_test', 'org_identifiers', 'sword_deposit', 'pub_deposit'
         ]
         super(TestFrontEnd, cls).setUpClass()

    @app_decorator
    def tearDown(self):
        self.logout()
        super(TestFrontEnd, self).tearDown()

    # @app_decorator
    def login(self, username="admin", password="admin", follow_redirects=True):
        return self.test_client.post(url_for('account.login'), data={
            "username": username,
            "password": password
        }, follow_redirects=follow_redirects)

    # @app_decorator
    def logout(self):
        return self.test_client.get(url_for("account.logout"), follow_redirects=True)

    @staticmethod
    def account_with_password(password, matching_config=None, account_type="repo", org_only=False):
        """
        Create an account with a given password of a certain account type

        :param password: Password to set on the account
        :param matching_config: Matching config object
        :param account_type: Type of account to return, defaults to a live repository account
        :param org_only: Boolean - True only return Org-Acc object otherwise return Tuple

        :return: Org-Account object if org_only is True
                 OTHERWISE Tuple: (Org-Account object, Admin-User-acc object, API-key-User-acc object)
        """
        if account_type == "pub":
            org_or_tuple = AccountFactory.publisher_account(password=password, org_only=org_only)
        else:
            if matching_config is None:
                matching_config = True
            org_or_tuple = AccountFactory.repo_account(matching_config=matching_config, password=password, org_only=org_only)
        return org_or_tuple

    def partial_post(self, view_path, **kwargs):
        # Make a partial of post with the api_key added to url_for - less writing this way.
        return partial(self.test_client.post, url_for(view_path, **kwargs))

    @staticmethod
    def stripped_text_by_selector(html, selector):
        return [strip_bad_text(item.text) for item in html.find_all(selector)]

    def _test_links_in_html(self, html, page):
        """
        helper function, for a collection of html, finds all links and checks that they're
        valid web links, raises a relevant exception with useful error message if not

        :param html: Page of html we're looking for
        :param page: The name of the page we're looking at
        """
        links_href_list = [a_el.get("href") for a_el in html.find_all("a")]
        external_links_set = set()
        internal_links_set = set()
        for link in links_href_list:
            if link:
                if link.startswith("http"):
                    external_links_set.add(link)
                # an internal link
                elif link.startswith("/") and not link.startswith("//"):
                    internal_links_set.add(link)

        # make requests against external links, raise a relevant exception upon failure
        for link in external_links_set:
            try:
                status_code = requests.get(link).status_code
                # Allow redirects
                if status_code // 100 >= 4:
                    warnings.warn(f"External link on page about.{page} failed: {link}")
            except OSError:  # Includes TimeoutError, ConnectionError and any other HTTP related error
                # sometimes Python gives us an exception rather than a 400, etc..
                warnings.warn(f"External link on page about.{page} failed: {link}")
        # make requests against internal links, raise a relevant exception upon failure
        for link in internal_links_set:
            status_code = self.test_client.get(link).status_code
            # Allow redirects
            if status_code // 100 >= 4:
                raise Exception(f"Internal link on page about.{page} failed: {link}")

    def assert_html_title(self, url, title,
                          title_suffix=' - Jisc Publications Router',
                          method='get', post_data=None):
        """
        Helper to assert that the correct <title> text is present in the response HTML generated
        from calling a view.

        :param url: The URL to fetch.
        :param title: Test string to compare against the title text.
        :param title_suffix: An optional string that is appended to the end of 'title', so the
               test string becomes '[title][title_suffix]'.
        :param method: Name of the HTTP method to use.
        :param post_data: data to pass to POST requests.
        :return: None
        """
        test_string = f"{title}{title_suffix}"

        response = self.test_client.get(url) if method == 'get' else self.test_client.post(url, data=post_data)
        html = response_to_html(response)
        title_text = html.find('title').text
        assert test_string, title_text


class TestFrontEndAnyone(TestFrontEnd):
    # tests which pertain to views for any user of our website (without or with permissions)
    @app_decorator
    def test_about_links(self):
        # Test all links on the various about pages, including embedded links
        response = self.test_client.get(url_for("about.index"))
        html = response_to_html(response)
        # the header and footer are the same for all about pages, so we'll just test these once
        html_header = html.find("header")
        self._test_links_in_html(html_header, "header")
        html_footer = html.find("footer")
        self._test_links_in_html(html_footer, "footer")
        # may as well test the index page whilst we have the html for it
        html_index_body = html.find("main").find("div")
        self._test_links_in_html(html_index_body, "index")
        # list of all pages on the about page, test the body of each
        pages = ["institutions", "publishers", "resources", "providerlist", "startupguide", "recipientlist"]
        for page in pages:
            response = self.test_client.get(url_for(f"about.{page}"))
            html_body = response_to_html(response).find("main").find("div")
            self._test_links_in_html(html_body, page)

    @app_decorator
    def test_login(self):
        # Test whether login works
        response = self.login(follow_redirects=False)
        assert response.status_code == 302
        # Confirm redirected to admin organisation account page
        assert response.location == f"/account/{self.admin_user_acc.acc_org.uuid}"

    @app_decorator
    def test_login_fail(self):
        # Test what happens when we have a bad login
        response = self.login("notanaccount", "badpassword")
        html = response_to_html(response)
        assert response.status_code == 200
        flash_element = html.find(name="article", attrs={"id": "flash-1"})
        assert "Incorrect username/password." in flash_element.text.strip()

    @app_decorator
    def test_login_deleted_account(self):
        # Create REPO account
        org_acc, org_admin_user, api_user, std_user, ro_user =\
            self.account_with_password("strongpassword", account_type="repo")
        assert org_acc.deleted_date is None

        # Log in as an admin user to delete the Org account & related User-accounts created above
        self.login()
        self.test_client.delete(url_for('account.delete_org_acc', org_uuid=org_acc.uuid))
        self.logout()
        # retrieve Org account record after deleting it (deletion sets the deletion date)
        test_ac = AccOrg.pull(org_acc.id)
        assert test_ac.deleted_date is not None
        assert test_ac.contact_email is None

        # Retrieve User accounts and ensure they are all deleted too (not API-User, which has no db record)
        for user_acc in (org_admin_user, std_user, ro_user):
            # Retrieve Admin User account record
            test_user_ac = AccUser.pull(user_acc.id)
            assert test_user_ac.deleted_date is not None
            assert test_user_ac.username.startswith("DELETED_")

        response = self.login(test_user_ac.username, "strongpassword", False)
        # If login is successful should have a 302 redirect HTML status; so we expect something else
        assert response.status_code != 302
        html = response_to_html(response)
        assert "Incorrect username/password." == html.find("article", id="flash-1").text.strip()

    @app_decorator
    def test_recipient_list(self):
        # Test that live accounts turn up on the recipient list (/about/recipientlist) page
        repo = self.account_with_password("strongpassword", org_only=True)
        cache.clear()   # Need to clear cache, because recipientlist page is cached
        # Turn on the account
        repo.repository_data.repository_activate()
        response = self.test_client.get(url_for("about.recipientlist"))

        # Account Org-name should be in the recipient list
        html = response_to_html(response)
        institutions_div = html.find("div", attrs={"id": "institutions"}).find("tbody")
        assert repo.org_name in institutions_div.get_text(separator="|", strip=True)

        # Turn off the account
        repo.repository_data.repository_off()
        repo.update()
        cache.clear()   # Need to clear cache, because recipientlist page is cached
        response = self.test_client.get(url_for("about.recipientlist"))

        # Account Org-name should NOT be in the recipient list
        html = response_to_html(response)
        institutions_div = html.find("div", attrs={"id": "institutions"}).find("tbody")
        assert repo.org_name not in institutions_div.get_text(separator="|", strip=True)

    @app_decorator
    def test_accessibility_statement(self):
        # Test that the accessibility statement view works and is linked to from the correct
        # page.

        # 1. Check the view can be loaded and has some content.
        accessibility_url = url_for('website.accessibility', _external=False)
        response = self.test_client.get(accessibility_url)
        html = response_to_html(response)
        title = html.find("title")
        assert title.text.startswith("Accessibility Statement")

        # 2. Check link is present in the footer. The footer is used on every page so justs check
        # the index.
        response = self.test_client.get(url_for("index"))
        html = response_to_html(response)
        assert html.find("title").text == "Jisc Publications Router"
        assert html.find("footer").find('a', attrs={'href': accessibility_url}, string='Accessibility')


class TestFrontEndRepositories(TestFrontEnd):
    # tests which pertain to views relevant for a repository user of the front end

    @staticmethod
    def create_csv_file_for_match_params(*bytes_name_list, other_value=" other  ", params_dict=None):
        if params_dict is None:
            list_length = len(bytes_name_list)
            data_str = "{}\n{}\n{}".format(
                ",".join(bytes_name_list),
                ",".join([".+"] * list_length),
                ",".join([other_value] * list_length)
            )
        else:
            params_dict = OrderedDict(params_dict)
            data_rows = [",".join([f'"{k}"' for k in params_dict.keys()])]
            row_count = 0
            data_found = True
            while data_found:
                data_found = False
                data_row = []
                for v_list in params_dict.values():
                    try:
                        data_row.append(f'"{v_list[row_count]}"')
                        data_found = True
                    except IndexError:
                        data_row.append('""')
                if data_found:
                    data_rows.append(",".join(data_row))
                    row_count += 1
            data_str = "\n".join(data_rows)
        return AlwaysBytesIO(data_str)

    @app_decorator
    def test_repository_org_acc_pg_tabs_view_for_all_user_types(self):
        """
        Test that repository users of types Org-admin, Standard, Read-only can view Organisation account page with
        expected sections & submission buttons.
        @return:
        """

        # set up the test Repository users
        password = "strongpassword"
        org_acc, org_admin_user, api_user, std_user, ro_user = self.account_with_password(password, account_type="repo")

        # Login as Org-admin
        response = self.login(org_admin_user.username, password, False)
        # _external=False causes relative URL (without scheme & domain) to be returned
        assert response.headers.get("location") == url_for('account.disp_org_acc', org_uuid=org_acc.uuid, _external=False)

        # start at the basic account management page
        response = self.test_client.get(url_for('account.disp_org_acc', org_uuid=org_acc.uuid))
        # get all html on this page
        html = response_to_html(response)
        # about is the leftmost element, account ought to be next to it
        about_el, account_el = html.find_all("div", class_="submenu submenu--left")
        # these elements are in the order in which they appear on the navbar
        menu_els = account_el.find_all("a")
        menu_els_text = [el.text for el in menu_els]
        assert menu_els_text == ['Organisation account',
                                 'Matched notifications',
                                 'Matching parameters',
                                 'Sources settings',
                                 'Connection settings',
                                 'Account settings',
                                 'User account',
                                 'List users',
                                 'Add user']

        main_el = html.find("main", id="main")

        # make sure the page contains divs with the correct ids so that the links work
        assert main_el.find("h2", id="users") is not None
        assert main_el.find("div", id="manage_matching") is not None
        assert main_el.find("div", id="manage_duplicates") is not None
        assert main_el.find("div", id="manage_sources") is not None
        assert main_el.find("div", id="manage_connection") is not None
        assert main_el.find("div", id="sword_history") is not None
        assert main_el.find("div", id="manage_account") is not None

        # check both links which lead to other pages actually work when clicked
        response = self.test_client.get(menu_els[1].get("href"))    # Matched notifications
        assert response.status_code == 200
        assert "<title>Notification History" in response.text

        response = self.test_client.get(menu_els[2].get("href"))    # Matching params
        assert response.status_code == 200
        assert "<title>View Matching Parameters" in response.text

        response = self.test_client.get(menu_els[6].get("href"))
        assert response.status_code == 200
        assert "<title>User Details" in response.text

        response = self.test_client.get(menu_els[7].get("href"))
        assert response.status_code == 200
        assert "<title>List Users" in response.text

        response = self.test_client.get(menu_els[8].get("href"))
        assert response.status_code == 200
        assert "<title>Add User" in response.text

        self.logout()

        ## Login as standard user

        response = self.login(std_user.username, password)  # Follow redirects, so account page is displayed
        # get all html for this page
        html = response_to_html(response)
        # about is the leftmost element, account ought to be next to it
        about_el, account_el = html.find_all("div", class_="submenu submenu--left")
        # these elements are the order in which they appear on the navbar
        menu_els = account_el.find_all("a")
        menu_els_text = [el.text for el in menu_els]
        assert menu_els_text == ['Organisation account',
                                 'Matched notifications',
                                 'Matching parameters',
                                 'Sources settings',
                                 'Connection settings',
                                 'Account settings',
                                 'User account']

        main_el = html.find("main", id="main")

        # Page should NOT have users section
        assert main_el.find("h2", id="users") is None

        # make sure the page contains divs with the correct ids so that the #links work
        # And also that <Update> buttons are present
        match_sect = main_el.find("div", id="manage_matching")
        assert match_sect is not None
        assert match_sect.find("button", id="max_age") is not None

        dups_sect = main_el.find("div", id="manage_duplicates")
        assert dups_sect is not None
        assert dups_sect.find("button", id="update_dups") is not None

        sources_sect = main_el.find("div", id="manage_sources")
        assert sources_sect is not None
        assert sources_sect.find("button", id="save_srcs") is not None

        conn_sect = main_el.find("div", id="manage_connection")
        assert conn_sect is not None
        assert conn_sect.find("button", id="update_conn") is not None

        assert main_el.find("div", id="sword_history") is not None

        acc_sect = main_el.find("div", id="manage_account")
        assert acc_sect is not None
        assert acc_sect.find("button", id="update_general") is not None

        self.logout()

        ## Login as Read-Only user

        response = self.login(ro_user.username, password)  # Follow redirects, so account page is displayed
        # get all html for this page
        html = response_to_html(response)
        # about is the leftmost element, account ought to be next to it
        about_el, account_el = html.find_all("div", class_="submenu submenu--left")
        # these elements are the order in which they appear on the navbar
        menu_els = account_el.find_all("a")
        menu_els_text = [el.text for el in menu_els]
        assert menu_els_text == ['Organisation account',
                                 'Matched notifications',
                                 'Matching parameters',
                                 'Sources settings',
                                 'Connection settings',
                                 'Account settings',
                                 'User account']

        main_el = html.find("main", id="main")

        # Page should NOT have users section
        assert main_el.find("h2", id="users") is None

        # make sure the page contains divs with the correct ids so that the #links work
        # And also that <Update> buttons are NOT present
        match_sect = main_el.find("div", id="manage_matching")
        assert match_sect is not None
        assert match_sect.find("button", id="max_age") is None

        dups_sect = main_el.find("div", id="manage_duplicates")
        assert dups_sect is not None
        assert dups_sect.find("button", id="update_dups") is None

        sources_sect = main_el.find("div", id="manage_sources")
        assert sources_sect is not None
        assert sources_sect.find("button", id="save_srcs") is None

        conn_sect = main_el.find("div", id="manage_connection")
        assert conn_sect is not None
        assert conn_sect.find("button", id="save_srcs") is None

        assert main_el.find("div", id="sword_history") is not None

        acc_sect = main_el.find("div", id="manage_account")
        assert acc_sect is not None
        assert acc_sect.find("button", id="update_general") is None

    @app_decorator
    def test_match_params_as_std_user(self):
        org_acc, org_admin_user, api_user, std_user, ro_user = self.account_with_password("strongpassword", account_type="repo")

        # Test whether the match params upload works with Standard User
        self.login(std_user.username, "strongpassword")

        partial_post = self.partial_post("account.set_match_params", org_uuid=org_acc.uuid)
        # Create a matching params CSV file that, adds the column headings listed below as the first row, and follows
        # this with 2 rows, the first row containing  ".+" in each column, the 2nd row containing "other" in each column
        csv_file = self.create_csv_file_for_match_params(
            "Name Variants",
            "Domains",
            "Postcodes",
            "Grant Numbers",
            "ORCIDS",
            "Author Emails"
        )

        # sleep(1)
        response = partial_post(data={"file": (csv_file, "csvfile.csv", "text/csv")}, follow_redirects=True)
        assert response.status_code == 200
        matching_params = AccRepoMatchParams.pull(org_acc.id)
        expected_test_results = {".+", "other"}
        assert set(matching_params.grants) == expected_test_results
        assert set(matching_params.name_variants) == expected_test_results
        assert set(matching_params.postcodes) == expected_test_results
        assert set(matching_params.domains) == expected_test_results
        assert set(matching_params.author_orcids) == expected_test_results
        assert len(matching_params.author_orcids) == 2
        assert len(matching_params.author_emails) == 0
        last_updated = matching_params.last_updated

        # Try again with different names and ordering to make sure it still works
        csv_file_with_different_names = self.create_csv_file_for_match_params(
            "Postcode List",
            "contributor emails",
            "GRANTS",
            "name variants",
            # "orcids",
            "Domain Names",
            other_value=" bingo "
        )

        sleep(1)
        response = partial_post(data={"file": (csv_file_with_different_names, "csvfile.csv", "text/csv")},
                                follow_redirects=True)
        assert response.status_code == 200
        matching_params = AccRepoMatchParams.pull(org_acc.id)
        new_results = {".+", "bingo"}
        assert set(matching_params.grants) == new_results
        assert set(matching_params.name_variants) == new_results
        assert set(matching_params.postcodes) == new_results
        assert set(matching_params.domains) == new_results
        # Orcids should NOT have been changed
        assert set(matching_params.author_orcids) == expected_test_results
        assert len(matching_params.author_orcids) == 2
        assert len(matching_params.author_emails) == 0
        assert matching_params.last_updated > last_updated
        cpy_matching_params = matching_params
        # Try again with garbage and missing config
        csv_file_with_garbage = self.create_csv_file_for_match_params(
            "postcode",
            "",
            "nonsense",
            "jisc id",
            "name variants",
            "domain names",
            "emails",
            "garbage"
        )

        sleep(1)
        response = partial_post(data={"file": (csv_file_with_garbage, "csvfile.csv", "text/csv")}, follow_redirects=True)
        assert "Matching parameters CSV file contained an unrecognized column header: 'nonsense'" in response.text
        # Check that no update occurred - ORIGINAL record should remain

        matching_params = AccRepoMatchParams.pull(org_acc.id)
        assert matching_params.last_updated == cpy_matching_params.last_updated
        assert matching_params.matching_config == cpy_matching_params.matching_config

        # Confirm duplicates removed

        csv_file = self.create_csv_file_for_match_params(params_dict={
            "name variants": ["  Oxford University  ", "University  of Oxford", "SHOULD BE REMOVED, Oxford University"],
            "": [],
            "postcodes": ["BS1 1SB", "LS2   2SL"],
            "domains": ["ox.ac.uk", "should-be-removed.ox.ac.uk", "http://cam.ac.uk/something",
                        "HTTP://UPPERX.AC.UK/OTHER", "https://other.ac.uk/what"],
            "grants": [" yyybbb-123 ", "abcde-321", " 2SPACE  grant "],
            "orcids": [" 0000-0001-2345-6789 ", "CCCC-0001-2345-6789"],
            "emails": [" some.one@gmail.com    ", "ALL.CAPITAL@GMAIL.COM", "should-be-removed@ox.ac.uk"],
            "organisation identifiers": [" ISN: 0001 0002 0003 0004", "https://ror.org/0524sp257", "ROR: 0524sp257", "RIN: 1234"]
        })
        # sleep(1)
        response = partial_post(data={"file": (csv_file, "csvfile.csv", "text/csv")}, follow_redirects=True)
        matching_params = AccRepoMatchParams.pull(org_acc.id)
        assert matching_params.grants == sorted(['yyybbb-123', 'abcde-321', '2SPACE grant'])
        assert matching_params.name_variants == sorted(['University of Oxford', 'Oxford University'], key=len)
        assert matching_params.postcodes == sorted(['BS1 1SB', 'LS2 2SL'])
        assert matching_params.domains == sorted(['other.ac.uk', 'upperx.ac.uk', 'cam.ac.uk', 'ox.ac.uk'], key=len)
        assert matching_params.author_emails == sorted(['all.capital@gmail.com', 'some.one@gmail.com'])
        assert matching_params.author_orcids == sorted(['0000-0001-2345-6789', 'CCCC-0001-2345-6789'])
        assert matching_params.org_ids == sorted(["ISNI:0001000200030004", "ROR:0524sp257", 'RINGGOLD:1234'])

        # Confirm partial data load works - Results should be same as previous values EXCEPT for
        # Changed ORCIDS, no emails, no org ids, no postcodes

        csv_file = self.create_csv_file_for_match_params(params_dict={
            "ORCIDS": ["1111-2222-3333-4444", "5555-6666-7777-8888"],
            # The following should be removed because previously loaded params include domain "ox.ac.uk"
            "emails": ["should-be-removed@ox.ac.uk", "another-should-be-removed@ox.ac.uk"],
            "Organisation Identifiers": [],
            "": [],
            "Postcodes": []
        })
        response = partial_post(data={"file": (csv_file, "csvfile.csv", "text/csv")}, follow_redirects=True)
        matching_params = AccRepoMatchParams.pull(org_acc.id)
        # Unchanged values
        assert matching_params.grants == sorted(['yyybbb-123', 'abcde-321', '2SPACE grant'])
        assert matching_params.name_variants == sorted(['University of Oxford', 'Oxford University'], key=len)
        assert matching_params.domains == sorted(['other.ac.uk', 'upperx.ac.uk', 'cam.ac.uk', 'ox.ac.uk'], key=len)
        # Changed values
        assert matching_params.postcodes == []
        assert matching_params.author_emails == []
        assert matching_params.author_orcids == sorted(["1111-2222-3333-4444", "5555-6666-7777-8888"])
        assert matching_params.org_ids == []

        ## Test update functions used by API (note that actual API requests are tested in file `test_api.py`) ##

        # Full set of params #
        test_json_matching_params = {
            "name_variants": ["  Cambridge University  ", "University  of Cambridge", "SHOULD BE REMOVED, Cambridge University"],
            "postcodes": ["BS1 1SB", "LS2   2SL"],
            "domains": ["ox.ac.uk", "should-be-removed.ox.ac.uk", "http://cam.ac.uk/something", "HTTP://UPPERX.AC.UK/OTHER", "https://other.ac.uk/what"],
            "grants": [" yyybbb-123 ", "abcde-321", " 2SPACE  grant "],
            "orcids": [" 9999-0001-2345-6789 ", "DDDD-0001-2345-6789"],
            "emails": [" some.one@gmail.com    ", "ALL.CAPITAL@GMAIL.COM", "should-be-removed@ox.ac.uk"],
            "org_ids": [" ISN: 1111 0002 0003 0004", "https://ror.org/9999sp257", "ROR: 9999sp257", "RIN: 6789"]
        }
        loaded_keys, removed, match_params_obj = AccRepoMatchParams.update_match_params(
            org_acc.id, org_acc.org_name, org_acc.uuid, jsoncontent=test_json_matching_params)
        matching_params = AccRepoMatchParams.pull(org_acc.id)
        assert matching_params.grants == sorted(['yyybbb-123', 'abcde-321', '2SPACE grant'])
        assert matching_params.name_variants == sorted(['University of Cambridge', 'Cambridge University'], key=len)
        assert matching_params.postcodes == sorted(['BS1 1SB', 'LS2 2SL'])
        assert matching_params.domains == sorted(['other.ac.uk', 'upperx.ac.uk', 'cam.ac.uk', 'ox.ac.uk'], key=len)
        assert matching_params.author_emails == sorted(['all.capital@gmail.com', 'some.one@gmail.com'])
        assert matching_params.author_orcids == sorted(['9999-0001-2345-6789', 'DDDD-0001-2345-6789'])
        assert matching_params.org_ids == sorted(["ISNI:1111000200030004", "ROR:9999sp257", 'RINGGOLD:6789'])
        assert len(loaded_keys) == 7
        assert len(removed) == 3

        # Partial set of params #
        test_json_matching_params = {
            "grants": [],
            "orcids": [" 8888-0001-2345-6789 ", "EEEE-0001-2345-6789"],
            "emails": ["should-be-removed@ox.ac.uk", "also-should-be-removed@ox.ac.uk"],
            "org_ids": ["RINGGOLD: 6789"]
        }
        loaded_keys, removed, match_params_obj = AccRepoMatchParams.update_match_params(
            org_acc.id, org_acc.org_name, org_acc.uuid, jsoncontent=test_json_matching_params)
        matching_params = AccRepoMatchParams.pull(org_acc.id)
        assert matching_params.grants == []
        assert matching_params.name_variants == sorted(['University of Cambridge', 'Cambridge University'], key=len)
        assert matching_params.postcodes == sorted(['BS1 1SB', 'LS2 2SL'])
        assert matching_params.domains == sorted(['other.ac.uk', 'upperx.ac.uk', 'cam.ac.uk', 'ox.ac.uk'], key=len)
        assert matching_params.author_emails == []
        assert matching_params.author_orcids == sorted(['8888-0001-2345-6789', 'EEEE-0001-2345-6789'])
        assert matching_params.org_ids == ['RINGGOLD:6789']
        assert len(loaded_keys) == 4
        assert len(removed) == 2

    @app_decorator
    def test_match_params_download_as_org_admin_and_ro_user(self):
        """
        Test downloading matching parameters CSV for a given account
        """
        org_acc, org_admin_user, api_user, std_user, ro_user = self.account_with_password(
            "strongpassword",
            account_type="repo",
            matching_config={"name_variants": ["first", "second", "third"],
                             "postcodes": ["first"],
                             "emails": ["first", "second"],
                             "orcids": ["first"]}
            )
        self.login(org_admin_user.username, "strongpassword")

        url = url_for("account.match_params_as_csv", org_uuid=org_acc.uuid)

        expected_data = (b"Name Variants,Domains,Postcodes,Grant Numbers,ORCIDs,Author Emails,Organisation Identifiers\r\n"
                         b"third,,first,,first,second,\r\nsecond,,,,,first,\r\nfirst,,,,,,\r\n")
        response = self.test_client.get(url)
        assert response.status_code == 200
        assert response.data == expected_data

        self.logout()

        # Now as read-only user
        self.login(ro_user.username, "strongpassword")

        response = self.test_client.get(url)
        assert response.status_code == 200
        assert response.data == expected_data

    @app_decorator
    def test_other_match_settings(self):
        # Test max pub age endpoint
        org_acc, org_admin_user, api_user, std_user, ro_user = self.account_with_password("strongpassword", account_type="repo")
        self.login(std_user.username, "strongpassword")

        partial_post = self.partial_post("account.update_other_match_params", org_uuid=org_acc.uuid)
        response = partial_post(data={"pub_years": 1}, follow_redirects=True)
        repo_data = AccOrg.pull(org_acc.id).repository_data
        html = response_to_html(response)
        assert "Successfully updated maximum age" == html.find("article", id="flash-1").text.strip()

        assert repo_data.max_pub_age == 1

        # Remove max_pub_age (set to "")
        response = partial_post(data={"pub_years": ""}, follow_redirects=True)
        assert response.status_code == 200
        html = response_to_html(response)
        repo_data = AccOrg.pull(org_acc.id).repository_data
        assert "Successfully updated maximum age" == html.find("article", id="flash-1").text.strip()
        assert not repo_data.max_pub_age

        response = partial_post(data={"pub_years": "Garbage Data"}, follow_redirects=True)
        assert response.status_code == 200
        html = response_to_html(response)
        assert "Maximum age must be an integer between 1 and 100, or blank." == html.find("article", id="flash-1").text.strip()

        self.logout()

        # Now attempt as Read-Only user - Should FAIL

        self.login(ro_user.username, "strongpassword")

        response = partial_post(data={"pub_years": 9}, follow_redirects=False)

        # Request fails because Read-Only user cannot POST.
        # The code would attempt to redirect to request.referrer, flashing the error message "Your account does not have
        # permission to perform this function.", BUT request.referrer is not set in this test-case.  Hence follow_redirects
        # is set to False above, and the best we can do is look for 302 redirect code
        assert response.status_code == 302
        # Confirm max_pub_age has NOT been updated
        repo_data = AccOrg.pull(org_acc.id).repository_data
        assert not repo_data.max_pub_age

    @app_decorator
    def test_match_regex_display(self):
        # Test that regex matching params containing characters like "<" are properly rendered with conversion to HTML entities taking place where needed
        # initalise repo account with various regex name variants
        test_matching_params = {
            "name_variants": [
                "q(?!u)", # negative lookahead
                "q(?=u)", # postitive lookahead
                "(?<!a)b", # negative lookbehind
                "(?<=a)b", # positive lookbehind
                "&<>‘”" # various markup escape characters
            ],
            "postcodes": [],
            "domains": [],
            "grants": [],
            "orcids": [],
            "emails": []
        }
        org_acc, org_admin_user, api_user, std_user, ro_user = self.account_with_password("strongpassword", matching_config=test_matching_params, account_type="repo")
        self.login(org_admin_user.username, "strongpassword")

        # get name_variants matching params
        test_names = [name for name in test_matching_params["name_variants"]]

        # get page, bs4 object
        response = self.test_client.get(url_for("account.view_match_params", repo_uuid=org_acc.uuid))
        html_response = response_to_html(response)
        # Get name_variant libxml elements 
        name_vars_lxml = html_response.find("table", id="name_variants").find_all("td")
        name_vars = [name.text for name in name_vars_lxml]

        # Confirm that displayed names correspond to expected
        assert name_vars.sort() == test_names.sort()


class TestFrontEndPublishers(TestFrontEnd):

    @app_decorator
    def test_publisher_org_acc_pg_tabs_view_for_all_user_types(self):
        """
        Test that publisher users of types Org-admin, Standard, Read-only can view Organisation account page with
        expected sections & submission buttons.
        @return:
        """
        # set up the test users
        password = "strongpassword"
        org_acc, org_admin_user, api_user, std_user, ro_user = self.account_with_password(password, account_type="pub")

        ## login as Org Administrator ##

        response = self.login(org_admin_user.username, password, False)
        # _external=False causes relative URL (without scheme & domain) to be returned
        assert response.headers.get("location") == url_for('account.disp_org_acc', org_uuid=org_acc.uuid, _external=False)

        # start at the basic account management page
        response = self.test_client.get(url_for('account.disp_org_acc', org_uuid=org_acc.uuid))
        # get all html for this page
        html = response_to_html(response)
        # about is the leftmost element, account ought to be next to it
        about_el, account_el = html.find_all("div", class_="submenu submenu--left")
        # these elements are the order in which they appear on the navbar
        menu_els = account_el.find_all("a")
        menu_els_text = [el.text for el in menu_els]
        assert menu_els_text == [
            'Organisation account',
            'Daily deposit summary',
            'Matched deposit history',
            'Default settings',
            'Account settings',
            'Automated test emails',
            'Automated test history',
            'Help connecting to Router',
            'User account',
            'List users',
            'Add user']

        main_el = html.find("main", id="main")

        # make sure the page contains divs with the correct ids so that the links work
        assert main_el.find("h2", id="users") is not None
        assert main_el.find("div", id="deposit_history") is not None
        assert main_el.find("div", id="manage_defaults") is not None
        assert main_el.find("div", id="manage_account") is not None
        assert main_el.find("div", id="manage_testing") is not None
        assert main_el.find("h2", id="ftp_help") is not None

        # check link which leads to other page actually works
        response = self.test_client.get(menu_els[1].get("href"))
        assert response.status_code == 200
        assert "<title>Daily deposit summary" in response.text

        response = self.test_client.get(menu_els[2].get("href"))
        assert response.status_code == 200
        assert "<title>Matched Deposit History" in response.text

        response = self.test_client.get(menu_els[6].get("href"))
        assert response.status_code == 200
        assert "<title>Test History" in response.text

        response = self.test_client.get(menu_els[8].get("href"))
        assert response.status_code == 200
        assert "<title>User Details" in response.text

        response = self.test_client.get(menu_els[9].get("href"))
        assert response.status_code == 200
        assert "<title>List Users" in response.text

        response = self.test_client.get(menu_els[10].get("href"))
        assert response.status_code == 200
        assert "<title>Add User" in response.text

        self.logout()

        ## Login as standard user

        response = self.login(std_user.username, password)  # Follow redirects, so account page is displayed
        # get all html for this page
        html = response_to_html(response)
        # about is the leftmost element, account ought to be next to it
        about_el, account_el = html.find_all("div", class_="submenu submenu--left")
        # these elements are the order in which they appear on the navbar
        menu_els = account_el.find_all("a")
        menu_els_text = [el.text for el in menu_els]
        assert menu_els_text == [
            'Organisation account',
            'Daily deposit summary',
            'Matched deposit history',
            'Default settings',
            'Account settings',
            'Automated test emails',
            'Automated test history',
            'Help connecting to Router',
            'User account']

        main_el = html.find("main", id="main")

        # Page should NOT have users section
        assert main_el.find("h2", id="users") is None
        
        # make sure the page contains divs with the correct ids so that the links work
        # And also that <Update> buttons are present
        assert main_el.find("div", id="deposit_history") is not None
        
        def_sect = main_el.find("div", id="manage_defaults")
        assert def_sect is not None
        assert def_sect.find("button", id="update_lic") is not None
        
        acc_sect = main_el.find("div", id="manage_account")
        assert acc_sect is not None
        assert acc_sect.find("button", id="update_general") is not None
        
        rep_sect = main_el.find("div", id="pub_reports")
        assert rep_sect is not None
        assert rep_sect.find("button", id="update_reports") is not None
        
        test_sect = main_el.find("div", id="manage_testing")
        assert test_sect is not None
        assert test_sect.find("button", id="update_test") is not None
        
        assert main_el.find("h2", id="ftp_help") is not None

        self.logout()

        ## Login as Read-Only user

        response = self.login(ro_user.username, password)  # Follow redirects, so account page is displayed
        # get all html for this page
        html = response_to_html(response)
        # about is the leftmost element, account ought to be next to it
        about_el, account_el = html.find_all("div", class_="submenu submenu--left")
        # these elements are the order in which they appear on the navbar
        menu_els = account_el.find_all("a")
        menu_els_text = [el.text for el in menu_els]
        assert menu_els_text == [
            'Organisation account',
            'Daily deposit summary',
            'Matched deposit history',
            'Default settings',
            'Account settings',
            'Automated test emails',
            'Automated test history',
            'Help connecting to Router',
            'User account']

        main_el = html.find("main", id="main")

        # Page should NOT have users section
        # <Update> buttons should all be absent
        assert main_el.find("h2", id="users") is None
        
        # make sure the page contains divs with the correct ids so that the links work
        assert main_el.find("div", id="deposit_history") is not None
        
        def_sect = main_el.find("div", id="manage_defaults")
        assert def_sect is not None
        assert def_sect.find("button", id="update_lic") is None     # No <Update> button
        
        acc_sect = main_el.find("div", id="manage_account")
        assert acc_sect is not None
        assert acc_sect.find("button", id="update_general") is None  # No <Update> button
        
        rep_sect = main_el.find("div", id="pub_reports")
        assert rep_sect is not None
        assert rep_sect.find("button", id="update_reports") is None  # No <Update> button
        
        test_sect = main_el.find("div", id="manage_testing")
        assert test_sect is not None
        assert test_sect.find("button", id="update_test") is None   # No <Update> button
        
        assert main_el.find("h2", id="ftp_help") is not None


class TestFrontEndAdmin(TestFrontEnd):
    # tests which pertain only to views available to the administrator

    @app_decorator
    def test_admin_account_pages(self):
        ## Account home page (displayed after logging in)
        response = self.login()
        html = response_to_html(response)
        main_el = html.find(name="main")

        assert "Admin account" == main_el.find("h1").text.strip()
        assert "Jisc Admin" == main_el.find("h2").text.strip()

        ## Manage accounts page

        response = self.test_client.get(url_for("account.index"))
        html = response_to_html(response)
        main_el = html.find("main", id="main")

        assert "Manage all organisations" == main_el.find("h1", id="stickme").text.strip()

        table_el = main_el.find("table")
        table_headings = list(table_el.find("thead").stripped_strings)
        col_heading_text = ["Account Type", "Organisation Name", "ID", "UUID", "Contact Email", "Repo s/w", "Status", "On/Off", "Manage", "Jump"]
        for hdr in table_headings:
            assert hdr == col_heading_text.pop(0)

        first_row_data = list(table_el.find("tbody").find("tr").stripped_strings)
        expected_row_data = ["admin", "Jisc Admin", "1"]
        for expected in expected_row_data:
            assert expected == first_row_data.pop(0)

    @app_decorator
    def test_admin_only_endpoints(self):
        # Test that a non admin user cannot access admin only endpoints
        password = "strongpassword"
        
        # Create Repository org account
        org_acc, org_admin_user, api_user, std_user, ro_user = self.account_with_password(password, account_type="repo")

        response = self.login(org_admin_user.username, password, False)
        # _external=False causes relative URL (without scheme & domain) to be returned
        assert response.headers.get("location") == url_for('account.disp_org_acc', org_uuid=org_acc.uuid, _external=False)

        assert self.test_client.get(url_for('account.disp_org_acc', org_uuid="admin")).status_code != 200
        assert self.test_client.get(url_for("admin.index")).status_code != 200
        assert self.test_client.get(url_for("reports.index")).status_code != 200
        assert self.test_client.get(url_for("account.index")).status_code != 200
        assert self.test_client.get(url_for("harvester.webservice")).status_code != 200

        # We should be able to access our own data though
        assert self.test_client.get(url_for('account.disp_org_acc', org_uuid=org_acc.uuid)).status_code == 200

    @app_decorator
    def test_live_accounts_on_index_pages(self):
        """
        Make sure a live account appears on the index page.
        """
        cache.clear()   # Need to clear cache, because index page is cached
        org_acc, org_admin_user, api_user, std_user, ro_user = self.account_with_password("password", account_type="repo")
        response = self.test_client.get(url_for("index"))
        html = response_to_html(response)

        # Organisation name should appear in Recent Partners panel
        recent_partners_el = html.find("main", id="main").find("div", class_="teaser__copy")
        assert org_acc.org_name in recent_partners_el.get_text(separator="|", strip=True)

    @app_decorator
    def test_admin_ajax_endpoint(self):
        """
        Test admin_ajax endpoint(./admin_ajax/<org_id>) works as expected for the 3 different functions that it supports:
            1) Toggle account status  On (OKAY) <--> Off
            2) Toggle repository account status  On (OKAY) <--> Failing
            3) Skip blocking notification.#
        :return:
        """
        # Create Repository org account
        org_acc = self.account_with_password("strongpassword", account_type="repo", org_only=True)

        # Note, because this is an admin only endpoint it uses the Org ID rather than UUID which is mostly used elsewhere.
        # Valid UUIDs by their nature are essentially unguessable, whereas valid IDs (sequential small integers) can
        # easily be guessed - so we only use them on GUI screens that are restricted to Jisc Admins.
        admin_ajax_partial_post = self.partial_post('account.admin_ajax', org_id=org_acc.id)

        self.login()     # Login as admin by default

        #
        ## 1 -- Toggle account status:  On (OKAY) <--> Off
        #
        org_acc.status = OKAY   # Initial setting
        org_acc.update()

        post_data = {"func": "toggle_account"}
        # Call the endpoint with toggle_account function
        response = admin_ajax_partial_post(
            data=json.dumps(post_data),
            headers={'Content-type':'application/json'},
            follow_redirects = True
        )
        assert response.status_code == 200
        assert response.json == {"status": "off"}

        updated_org_acc = AccOrg.pull(org_acc.id)
        assert updated_org_acc.status == OFF    # Toggled --> OFF

        # Call endpoint again
        response = admin_ajax_partial_post(
            data=json.dumps(post_data),
            headers={'Content-type': 'application/json'},
            follow_redirects=True
        )
        assert response.status_code == 200
        assert response.json == {"status": "okay"}

        updated_org_acc = AccOrg.pull(org_acc.id)
        assert updated_org_acc.status == OKAY   # Toggled ==> ON

        #
        ## 2 -- Toggle repository account status:  On (OKAY) <--> Failing
        #
        post_data = {"func": "toggle_repo_status"}
        # Call the endpoint with toggle_repo_status function
        response = admin_ajax_partial_post(
            data=json.dumps(post_data),
            headers={'Content-type':'application/json'},
            follow_redirects = True
        )
        assert response.status_code == 200
        assert response.json == {"status": "failing"}

        updated_org_acc = AccOrg.pull(org_acc.id)
        assert updated_org_acc.status == FAILING    # Toggled --> FAILING

        # Call toggle_repo_status endpoint again
        response = admin_ajax_partial_post(
            data=json.dumps(post_data),
            headers={'Content-type': 'application/json'},
            follow_redirects=True
        )
        assert response.status_code == 200
        assert response.json == {"status": "okay"}

        updated_org_acc = AccOrg.pull(org_acc.id)
        assert updated_org_acc.status == OKAY   # Toggled ==> ON

        #
        ## 3 -- Skip blocking notification.
        #       (This has various error cases to test).

        # Create Notification record and some SwordDeposit records containing errors
        note_dict = RoutedNotification(NotificationFactory.routed_notification(no_id_or_created=True)).insert()
        note_id = note_dict["id"]
        metadata_ok_dict = SwordFactory.create_deposit_rec(repo_id=org_acc.id, note_id=note_id, metadata_status=DEPOSITED)
        metadata_failed_dict = SwordFactory.create_deposit_rec(repo_id=org_acc.id, note_id=note_id, metadata_status=FAILED, err_msg="Error")
        metadata_failed_wrong_acc_dict = SwordFactory.create_deposit_rec(repo_id=999, note_id=note_id, metadata_status=FAILED, err_msg="Error - wrong acc")
        metadata_failed_wrong_note_dict = SwordFactory.create_deposit_rec(repo_id=org_acc.id, note_id=999, metadata_status=FAILED, err_msg="Error - wrong note")


        # 3.1 - Test absent parameters (note_id and err_id)

        post_data = {"func": "skip_blocking_note"}
        # Call the endpoint with skip_blocking_note function
        response = admin_ajax_partial_post(
            data=json.dumps(post_data),
            headers={'Content-type':'application/json'},
            follow_redirects = True
        )
        assert response.status_code == 400
        assert response.json == {'error': 'note_id and err_id fields are required'}

        # 3.2 - Test Repo org account not in Failing state

        # Provide values for required params
        post_data.update({"note_id": note_id, "err_id": metadata_ok_dict["id"]})
        # Call the endpoint with skip_blocking_note function
        response = admin_ajax_partial_post(
            data=json.dumps(post_data),
            headers={'Content-type':'application/json'},
            follow_redirects = True
        )
        assert response.status_code == 400
        assert "is not failing" in response.json['error']   # Get an error because the Repo account is NOT Failing

        # 3.3 - Test note_id <= last-deposited-note-id value

        org_acc.status = FAILING
        org_acc.repository_data.last_deposited_note_id = 99
        org_acc.update()
        # Call the endpoint with skip_blocking_note function
        response = admin_ajax_partial_post(
            data=json.dumps(post_data),
            headers={'Content-type':'application/json'},
            follow_redirects = True
        )
        assert response.status_code == 400
        assert response.json['error'] == 'The specified notification (ID 1) has previously been deposited or skipped'

        # 3.4 - Test note_id > last-deposited-note-id value

        org_acc.repository_data.last_deposited_note_id = 0
        org_acc.update()
        # Call the endpoint with skip_blocking_note function
        response = admin_ajax_partial_post(
            data=json.dumps(post_data),
            headers={'Content-type':'application/json'},
            follow_redirects = True
        )
        assert response.status_code == 400
        assert response.json['error'] == 'The specified SWORD deposit record (ID 1) is not for a metadata failure'

        # 3.5 - Failing Sword Deposit Rec is for a different institution than that specified in POST data

        post_data["err_id"] = metadata_failed_wrong_acc_dict["id"]
        # Call the endpoint with skip_blocking_note function
        response = admin_ajax_partial_post(
            data=json.dumps(post_data),
            headers={'Content-type':'application/json'},
            follow_redirects = True
        )
        assert response.status_code == 400
        assert "not for the specified institution" in response.json['error']

        # 3.6 - Failing Sword Deposit Rec is for a different notification  than that specified in POST data

        post_data["err_id"] = metadata_failed_wrong_note_dict["id"]
        # Call the endpoint with skip_blocking_note function
        response = admin_ajax_partial_post(
            data=json.dumps(post_data),
            headers={'Content-type':'application/json'},
            follow_redirects = True
        )
        assert response.status_code == 400
        assert "not for the specified notification" in response.json['error']

        # 3.7 - SUCCESS: Failing Sword Deposit Rec IS for the repository and notification specified in the POST parameters

        post_data["err_id"] = metadata_failed_dict["id"]
        # Call the endpoint with skip_blocking_note function
        response = admin_ajax_partial_post(
            data=json.dumps(post_data),
            headers={'Content-type':'application/json'},
            follow_redirects = True
        )
        assert response.status_code == 200
        assert f"Failing notification ID {note_id} has been skipped" in response.json['msg']
        updated_org_acc = AccOrg.pull(org_acc.id)
        assert updated_org_acc.status == OKAY    # Status has been changed to OKAY
        assert updated_org_acc.repository_data.last_deposited_note_id == note_id    # Last deposited note id has been updated


    @app_decorator
    def test_identifier_csv(self):
        # Test uploading an identifier CSV
        self.login()
        partial_post = self.partial_post("admin.identifiers")

        csv_file = AlwaysBytesIO(
            "FILE WITH IDS\n"   # Page title
            "\n"  # Blank like
            "ID,Institution\n"
            "3456,University of Nowhere\n"
            "1234,Some University\n"
            "6543,Other"
        )

        post_data = {
            "csv_file": (csv_file, "csvfile.csv", "text/csv"),
            "choices": "JISC"
        }

        response = partial_post(data=post_data, follow_redirects=True)
        assert response.status_code == 200

        html = response_to_html(response)

        flash_text = strip_bad_text(html.find("article").text)

        assert flash_text == "Successfully uploaded 3 JISC identifiers."

        list_of_ids = {identifier.value for identifier in Identifier.pull_all()}

        assert len(list_of_ids) == 3
        assert list_of_ids == {"3456", "1234", "6543"}

    @app_decorator
    def test_identifier_csv_download(self):
        # Test whether the CSV download for identifiers works
        self.login()

        identifier_factory = IdentifierFactory
        institution = "University of Nowhere"
        jisc = identifier_factory.make_jisc(institution)
        core = identifier_factory.make_core(institution)

        response = self.test_client.get(url_for('admin.identifiers'))
        assert response.status_code == 200
        assert response.content_type == "text/csv; charset=utf-8"

        csv_file = csv.reader(StringIO(response.data.decode("utf-8")))

        header = next(csv_file)
        assert header == ["Type", "Name", "ID"]

        jisc_row = next(csv_file)
        assert jisc_row == ["JISC", institution, jisc.value]

        core_row = next(csv_file)
        assert core_row == ["CORE", institution, core.value]

    @app_decorator
    def test_reports_live_institutions(self):
        # Test that institution reports turn up on the institution reports page (/reports/institutions)
        self.login()

        # Create a file for the institution reports
        path = "LIVE_report.csv"
        text = b"fakecsv"

        with open(self.report_path(path), "wb") as file:
            file.write(text)

        # Get the institution report list
        response = self.test_client.get(url_for("reports.institutions"))

        html = response_to_html(response)
        report_link_ul = html.find("main").find("ul")
        # The name 'LIVE_report.csv' should be there as it's in the folder created above
        assert "LIVE_report.csv" in report_link_ul.get_text(separator="|", strip=True)

        response = self.test_client.get(url_for("reports.serve_report", path=path))
        assert response.data == text

    @app_decorator
    def test_reports_test_institutions(self):
        self.login()

        # Create a file for the institution reports
        path = "TEST_report.csv"
        text = b"fakecsv"

        with open(self.report_path(path), "wb") as file:
            file.write(text)

        # Get the institution report list
        response = self.test_client.get(url_for("reports.test_institutions"))

        html = response_to_html(response)
        report_link_ul = html.find("main").find("ul")
        # The name 'TEST_report.csv' should be there as it's in the folder created above
        assert "TEST_report.csv" in report_link_ul.get_text(separator="|", strip=True)

        response = self.test_client.get(url_for("reports.serve_report", path=path))
        assert response.data == text

    @app_decorator
    def test_reports_publishers(self):
        # Test that publisher reports turn up on the publisher reports page (/reports/publishers)
        self.login()

        # Create a file for a publisher report
        path = os.path.join("publishers", "publishers_report.csv")
        text = b"fakecsv"

        os.makedirs(self.report_path("publishers"))

        with open(self.report_path(path), "wb") as file:
            file.write(text)

        # Get the publisher report list
        response = self.test_client.get(url_for("reports.publishers"))

        html = response_to_html(response)
        report_link_ul = html.find("main").find("ul")
        # The name 'publishers_report.csv' should be there as it's in the folder created above
        assert "publishers_report.csv" in report_link_ul.get_text(separator="|", strip=True)

        # Must replace slashes in case of windows
        response = self.test_client.get(url_for("reports.serve_report", path=path.replace("\\", "/")))
        assert response.data == text

    @app_decorator
    def test_reports_harvester(self):
        # Test that publisher reports turn up on the publisher reports page (/reports/publishers)
        self.login()

        # Create a file for a publisher report
        path = os.path.join("publishers", "harvester_report.csv")
        text = b"fakecsv"

        os.makedirs(self.report_path("publishers"))

        with open(self.report_path(path), "wb") as file:
            file.write(text)

        # Get the publisher report list
        response = self.test_client.get(url_for("reports.harvester"))

        html = response_to_html(response)
        report_link_ul = html.find("main").find("ul")
        # The name 'harvester_report.csv' should be there as it's in the folder created above
        assert "harvester_report.csv" in report_link_ul.get_text(separator="|", strip=True)

        # Must replace slashes in case of windows
        response = self.test_client.get(url_for("reports.serve_report", path=path.replace("\\", "/")))
        assert response.data == text

    @app_decorator
    def test_reports_all(self):
        # Test that the both publisher and institution reports turn up on the report index page (/reports/)
        # And that the links work for them
        self.login()

        live_inst_path = "LIVE_institutions.csv"
        test_inst_path = "TEST_institutions.csv"

        publisher_path = os.path.join("publishers", "publishers_report.csv")
        harvester_path = os.path.join("publishers", "harvester_report.csv")
        os.makedirs(self.report_path("publishers"))

        harvester_text = b"harvcsv"
        publisher_text = b"pubcsv"
        live_inst_text = b"instcsv"
        test_inst_text = b"testinstcsv"

        with open(self.report_path(live_inst_path), "wb") as file:
            file.write(live_inst_text)

        with open(self.report_path(test_inst_path), "wb") as file:
            file.write(test_inst_text)

        with open(self.report_path(publisher_path), "wb") as file:
            file.write(publisher_text)

        with open(self.report_path(harvester_path), "wb") as file:
            file.write(harvester_text)

        response = self.test_client.get(url_for("reports.index"))

        html = response_to_html(response)

        # Inside the .row.cms div, there will be two A links - these are our reports.
        # This div is inside the main panel on the report index webpage.
        # it's in this order because the publisher elements are below the insitution ones.
        live_inst_ele, test_inst_ele, publisher_ele, harvester_ele = html.find("div", class_="row cms").find_all("a")
        assert live_inst_ele.text == live_inst_path
        assert test_inst_ele.text == test_inst_path
        assert publisher_ele.text == os.path.basename(publisher_path)
        assert harvester_ele.text == os.path.basename(harvester_path)

        # Get the link from the a tag which should have the institution text inside
        response = self.test_client.get(live_inst_ele.get("href"))
        assert live_inst_text == response.data

        # Get the link from the a tag which should have the publisher text inside
        response = self.test_client.get(test_inst_ele.get("href"))
        assert test_inst_text == response.data

        response = self.test_client.get(publisher_ele.get("href"))
        assert publisher_text == response.data

        response = self.test_client.get(harvester_ele.get("href"))
        assert harvester_text == response.data


class TestTitles(TestFrontEnd):
    """
    Test the <title> rendered by the 'about' views.
    """

    @app_decorator
    def test_titles(self):
        self.assert_html_title(url_for('about.index'), 'About')

        self.assert_html_title(url_for('website.cookies'), 'Cookie Settings')

        self.assert_html_title(url_for('about.institutions'), 'Information for Institutions')

        self.assert_html_title(url_for('about.publishers'), 'Information for Publishers')

        self.assert_html_title(url_for('about.resources'), 'Technical Information')

        self.assert_html_title(url_for('about.providerlist'), 'List of Router Content Providers')

        self.assert_html_title(url_for('about.startupguide'), 'Start-up Guide For Institutions')

        self.assert_html_title(url_for('about.recipientlist'), 'List of Participating Institutions')

        login_url = url_for('account.login')
        self.assert_html_title(login_url, 'Login')
        self.assert_html_title(login_url, 'Login', method='post', post_data={'username': 'foo', 'password': 'bar'})

        self.assert_html_title(url_for('account.reset_token'), 'Request Password Reset')


def two_empty_lists():
    '''
    Used as a mock function to replace _get_publisher_and_harvester_report_filenames and
    _get_institution_report_filenames in TestReportsViewPageTitles tests.
    '''
    return [], []


class TestAdminTitles(TestFrontEnd):
    """
    Test the <title> rendered by the 'account' views.

    For some tests I've patched out the calls that talk to the database, but the
    @org_user_or_admin_org__gui decorator is too hard to patch, so for those tests we login first.
    """
    @app_decorator
    def test_titles(self):
        self.login()

        self.assert_html_title(url_for('admin.index'), 'Administration Panel')

        self.assert_html_title(url_for('account.index'), 'Manage all organisations')

        self.assert_html_title(url_for('account.manage_publishers'), 'Manage publishers')

        manage_repos_url = url_for('account.manage_repositories')

        # Manage ALL repositories
        self.assert_html_title(manage_repos_url, 'Manage repositories')

        # Manage ALL On repositories
        self.assert_html_title(manage_repos_url + '/on', 'Manage on repositories')

        # Manage ALL Off repositories
        self.assert_html_title(manage_repos_url + '/off', 'Manage off repositories')

        # Manage ALL Problem repositories
        self.assert_html_title(manage_repos_url + '/problem', 'Manage problem repositories')

        # Manage ALL live repositories
        self.assert_html_title(manage_repos_url + '/live', 'Manage live repositories')

        # Manage only ON live repositories
        self.assert_html_title(manage_repos_url + '/live/on', 'Manage live on repositories')

        # Manage only OFF live repositories
        self.assert_html_title(manage_repos_url + '/live/off', 'Manage live off repositories')

        # Manage only Problem test repositories
        self.assert_html_title(manage_repos_url + '/live/problem', 'Manage live problem repositories')

        # Manage ALL live repositories
        self.assert_html_title(manage_repos_url + '/test', 'Manage test repositories')

        # Manage only ON live repositories
        self.assert_html_title(manage_repos_url + '/test/on', 'Manage test on repositories')

        # Manage only OFF live repositories
        self.assert_html_title(manage_repos_url + '/test/off', 'Manage test off repositories')

        # Manage only Problem test repositories
        self.assert_html_title(manage_repos_url + '/test/problem', 'Manage test problem repositories')

        # Register account
        self.assert_html_title(url_for('account.register'), 'Register a New User')

    @patch('router.jper.views.reports._get_publisher_and_harvester_report_filenames', two_empty_lists)
    @patch('router.jper.views.reports._get_institution_report_filenames', two_empty_lists)
    @app_decorator
    def test_reports_titles(self):
        self.login()

        self.assert_html_title(url_for('reports.index'), 'Reports')

        self.assert_html_title(url_for('reports.publishers'), 'Publisher Reports')

        self.assert_html_title(url_for('reports.harvester'), 'Harvester Reports')

        self.assert_html_title(url_for('reports.test_institutions'), 'Test Institution Reports')

    @patch('router.jper.views.account._deposit_record_history_to_template_variables')
    @app_decorator
    def test_history(self, _to_template_vars):
        # Need to login because patching out @org_user_or_admin_org__gui is too hard.
        self.login()

        # Mock the return value of _deposit_record_history_to_template_variables - include only what
        # is needed to render the page.
        _to_template_vars.return_value = {'num_of_pages': 1, 'page': 1}

        self.assert_html_title(url_for('account.deposit_history', pub_uuid='admin'), 'Deposit History')

        self.assert_html_title(url_for('account.sword_deposit_history', repo_uuid='1234'), 'SWORD Deposit History')

        admin_acc = AccOrg.pull(1, wrap=False)
        self.assert_html_title(url_for('account.notifications', repo_uuid=admin_acc["uuid"]), 'Notification History')

    @patch('router.jper.views.account.PasswordUserForm')
    @patch('router.jper.views.account.AccUser.pull')
    @app_decorator
    def test_reset_password_post_invalid(self, account_pull, pwd_user_form):
        # Create mock for AccOrg.pull_by_username_contact
        account_pull.return_value.valid_reset_token.return_value = {'value': 'foo'}
        # Mock the PasswordUserForm and make it fail validation.
        pwd_user_form.return_value.validate.return_value = False

        url = url_for('account.reset_password', user_uuid='1234', token_val='foo')
        # POST
        self.assert_html_title(url, 'Reset Password', method='post')
        # PULL
        self.assert_html_title(url, 'Reset Password')

    @patch('router.jper.views.account._get_org_acc_by_uuid')
    @app_decorator
    def test_org_n_user_acc_non_admin(self, _get_org_acc_by_uuid):
        # Create a mock publisher Account that is returned by _get_org_acc_by_uuid. Supply enough details to get the page to render.
        def _has_role(role):
            return role == 'publisher'

        def _get_test_data_dict_for_form():
            return {
                "in_test": True,
                "test_start": "01/10/2020",
                "start_checkbox": True,
                "test_end": "",
                "end_checkbox": False,
                "test_type": "am",
                "test_report_emails": "test@here.com",
                "last_error": "14/11/2020",
                "last_ok": "17/11/2020",
                "num_err_tests": 16,
                "num_ok_tests": 7,
                "num_ok_since_last_err": 4,
                "route_note_checkbox": False
            }

        def _get_report_data_for_form():
            return {
                "report_format": "",     # Empty string --> No report
                "report_emails": [],
            }

        def _tech_contact_emails_string():
            return ""

        def _tech_and_users_emails_dict_lists():
            return {}

        acc = Mock()
        acc.org_name = 'Fake Org'
        acc.created = '2020-03-18T00:00:00Z'
        acc.live_date = '3500-03-20T00:00:00Z'
        acc.role = 'publisher'
        acc.has_role = _has_role
        acc.is_repository = False
        acc.is_publisher = True
        acc.org_status.return_value = 'off'
        acc.reset_token = None
        acc.publisher_data.get_test_data_dict_for_form = _get_test_data_dict_for_form
        acc.publisher_data.get_report_data_for_form = _get_report_data_for_form
        acc.tech_contact_emails_string = _tech_contact_emails_string
        acc.tech_and_users_emails_dict_lists = _tech_and_users_emails_dict_lists
        _get_org_acc_by_uuid.return_value = acc

        self.login()

        url = url_for('account.disp_org_acc', org_uuid='1234')
        self.assert_html_title(url, 'Account Details for Fake Org')


class TestHarvesterViewPageTitles(TestFrontEnd):
    """
    Test the <title> rendered by the 'harvester' views.
    """

    @app_decorator
    def setUp(self):
        super(TestHarvesterViewPageTitles, self).setUp()
        HarvesterTestUtils.create_default_ws_recs()
        self.login(follow_redirects=False)

    @app_decorator
    def tearDown(self):
        self.logout()
        super(TestHarvesterViewPageTitles, self).tearDown()

    @app_decorator
    def test_webservice(self):
        url = url_for('harvester.webservice')
        self.assert_html_title(url, 'Harvester Sources')

    @app_decorator
    def test_history(self):
        url = url_for('harvester.history')
        self.assert_html_title(url, 'Harvester History')

    @app_decorator
    def test_error(self):
        url = url_for('harvester.error')
        self.assert_html_title(url, 'Harvester Errors')

    @app_decorator
    def test_manage_get_edit(self):
        url = url_for('harvester.manage', webservice_id=1)
        self.assert_html_title(url, 'Edit harvester')

    @app_decorator
    def test_manage_get_add(self):
        url = url_for('harvester.manage', webservice_id=None)
        self.assert_html_title(url, 'Add harvester')

    @patch('router.jper.views.harvester.WebserviceForm')
    @app_decorator
    def test_manage_post_add_n_edit_validation_fail(self, webservice_form):
        # Patch Webservice.validate() to return False so the request is not redirected.
        webservice_form.return_value.validate.return_value = False

        url = url_for('harvester.manage', webservice_id=None)
        self.assert_html_title(url, 'Add harvester', method='post')

        url = url_for('harvester.manage', webservice_id=1)
        self.assert_html_title(url, 'Edit harvester', method='post')
