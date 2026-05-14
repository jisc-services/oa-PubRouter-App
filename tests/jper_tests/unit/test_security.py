"""
Tests for the security functions (which are normally invoked in view functions via decorators).

IMPORTANT limitation - these functions all use Organisation account API key to test the security, rather than
first logging in with username & password.

Tests each type of account against the security decorators to see if they work correctly.
"""
from flask import url_for
from functools import partial
from tests.fixtures.factory import AccountFactory, DEFAULT_PWD
from router.jper.web_main import app_decorator
from router.jper.security import ErrorMessages
from tests.jper_tests.fixtures.testcase import JPERTestCase


ADMIN_KEY = "admin"
INVALID_KEY = "SuperBadKey"
INVALID_UUID = "invalid_invalid_invalid_invalid_"

class TestSecurity(JPERTestCase):
    @classmethod
    def setUpClass(cls):
        # List the tables (by table name) needed for testing
        cls.tables_for_testing = ['account', 'acc_user', 'cms_ctl', 'cms_html', 'h_webservice', 'pub_deposit']
        super().setUpClass()

    @app_decorator
    def setUp(self):
        super().setUp()

        self.repository, self.repo_admin_user, self.repo_api_user, self.repo_std_user, self.repo_ro_user =\
            AccountFactory.repo_account(live=True, org_only=False)
        self.publisher, self.pub_admin_user, self.pub_api_user, self.pub_std_user, self.pub_ro_user =\
            AccountFactory.publisher_account(org_only=False)

    @app_decorator
    def login(self, username="admin", password="admin", follow_redirects=True):
        return self.test_client.post(url_for('account.login'), data={
            "username": username,
            "password": password
        }, follow_redirects=follow_redirects)

    @app_decorator
    def logout(self):
        return self.test_client.get(url_for("account.logout"), follow_redirects=True)

    # def get_response_gui(self, route):
    #     return self.test_client.get(url_for(route))

    @app_decorator
    def get_response_gui_org_uuid(self, route, org_uuid):
        return self.test_client.get(url_for(route, org_uuid=org_uuid))

    @app_decorator
    def post_response_gui_org_uuid(self, route, org_uuid):
        return self.test_client.post(url_for(route, org_uuid=org_uuid), data={})

    @app_decorator
    def get_response_gui_uuid_user_uuid(self, route, org_uuid, user_uuid):
        return self.test_client.get(url_for(route, org_uuid=org_uuid, user_uuid=user_uuid))

    @app_decorator
    def post_response_gui_uuid_user_uuid(self, route, org_uuid, user_uuid):
        return self.test_client.post(url_for(route, org_uuid=org_uuid, user_uuid=user_uuid), data={})

    # app_decorator is needed here so we have a new Context for each request, otherwise the login manager reuses the
    # previous user details instead of fetching user from database
    @app_decorator
    def get_response_with_apikey(self, route, api_key):
        return self.test_client.get(url_for(route, api_key=api_key))

    @app_decorator
    def get_response_with_apikey_org_uuid(self, route, org_uuid, api_key):
        return self.test_client.get(url_for(route, org_uuid=org_uuid, api_key=api_key))

    @app_decorator
    def get_response_with_apikey_org_uuid_user_uuid(self, route, org_uuid, user_uuid, api_key):
        return self.test_client.get(url_for(route, org_uuid=org_uuid, user_uuid=user_uuid, api_key=api_key))

    @staticmethod
    def validate_response(response, status_code, error_message=None):
        assert response.status_code == status_code
        if error_message:
            assert response.json["error"] == error_message

    ## GUI endpoints ##
    def test_admin_org_only__gui_with_apikey(self):
        """
        NOTE that use of API-Key always returns API-key User account + the Org Account
        @return:
        """
        admin_only_partial = partial(self.get_response_with_apikey, "security_gui.admin_org_only__gui")
        # Invalid key
        response = admin_only_partial(INVALID_KEY)
        self.validate_response(response, 302)   # Redirected to previous or user page

        # Publisher
        response = admin_only_partial(self.publisher.api_key)
        self.validate_response(response, 302)   # Redirected to previous or user page

        # Repository
        response = admin_only_partial(self.repository.api_key)
        self.validate_response(response, 302)   # Redirected to previous or user page

        # Admin
        response = admin_only_partial(ADMIN_KEY)
        self.validate_response(response, 200)

    def test_admin_org_only_or_401__gui_with_apikey(self):
        """
        NOTE that use of API-Key always returns API-key User account + the Org Account
        @return:
        """
        admin_only_partial = partial(self.get_response_with_apikey, "security_gui.admin_org_only_or_401__gui")
        # Invalid key
        response = admin_only_partial(INVALID_KEY)
        self.validate_response(response, 401)

        # Publisher
        response = admin_only_partial(self.publisher.api_key)
        self.validate_response(response, 403)

        # Repository
        response = admin_only_partial(self.repository.api_key)
        self.validate_response(response, 403)

        # Admin
        response = admin_only_partial(ADMIN_KEY)
        self.validate_response(response, 200)

    def test_org_user_or_admin_org__gui_with_apikey(self):
        """
        NOTE that use of API-Key always returns API-key User account + the Org Account
        @return:
        """
        request_partial = partial(self.get_response_with_apikey_org_uuid, "security_gui.org_user_or_admin_org__gui")
        # Invalid key
        response = request_partial(self.repository.uuid, INVALID_KEY)
        self.validate_response(response, 302)   # Redirected to Login page

        # Publisher
        response = request_partial(INVALID_UUID, self.publisher.api_key)
        self.validate_response(response, 302)   # Redirected to previous or user page

        # Publisher
        response = request_partial(self.publisher.uuid, self.publisher.api_key)
        self.validate_response(response, 200)
        assert response.json['o_orgname'] == self.publisher.org_name
        assert response.json['u_username'] == 'API-Key-user'

        # Repository
        response = request_partial(INVALID_UUID, self.repository.api_key)
        self.validate_response(response, 302)   # Redirected to previous or user page

        # Repository
        response = request_partial(self.repository.uuid, self.repository.api_key)
        self.validate_response(response, 200)
        assert response.json['o_orgname'] == self.repository.org_name
        assert response.json['u_username'] == 'API-Key-user'

        # Admin (ignores UUID)
        response = request_partial(INVALID_UUID, ADMIN_KEY)
        self.validate_response(response, 200)
        assert response.json['o_orgname'] == 'Jisc Admin'
        assert response.json['u_username'] == 'API-Key-user'

    def test_user_admin_or_admin_org__gui_with_apikey(self):
        """
        THIS TESTING IS LIMITED by fact that by making request using api-key always returns the NON-Org-admin APIkey User,
        so CANNOT test all permutations e.g. those involving logging in as an Org-Admin for a Publisher or Repository Account.

        @return:
        """
        request_partial = partial(self.get_response_with_apikey_org_uuid_user_uuid, "security_gui.user_admin_or_admin_org__gui")
        # Invalid API key
        response = request_partial(self.repository.uuid, self.repo_admin_user, INVALID_KEY)
        self.validate_response(response, 302)   # Redirected to Login page

        # Publisher, fails because NON-OrgAdmin APIKey-user is returned by API-key login process
        response = request_partial(self.publisher.uuid, self.pub_api_user.uuid, self.publisher.api_key)
        self.validate_response(response, 302)   # Redirected to previous or user page

        # Repository fails because NON-OrgAdmin APIKey-user is returned by API-key login process
        response = request_partial(self.repository.uuid, self.repo_api_user.uuid, self.repository.api_key)
        self.validate_response(response, 302)   # Redirected to previous or user page

        # Admin (ignores UUID)  - fails because API-Key user is Read-Only
        response = request_partial(INVALID_UUID, INVALID_UUID, ADMIN_KEY)
        self.validate_response(response, 302) # Redirected to last page

    def test_user_admin_or_admin_org__gui_with_login(self):
        """
        @return:
        """
        request_partial = partial(self.get_response_gui_uuid_user_uuid, "security_gui.user_admin_or_admin_org__gui")

        # Login as Admin Org (note that Admin accounts are automatically created outside of this file)
        self.login("admin", "admin")
        
        # Invalid ORG-UUID & USER-UUID - these are ignored because Org Ac is Admin
        response = request_partial(INVALID_UUID, INVALID_UUID)
        self.validate_response(response, 200)
        
        self.logout()

        # Login as Publisher Org-admin
        self.login(self.pub_admin_user.username, DEFAULT_PWD)
        
        # Publisher, logged in as Org-Admin, but provided ORG-UUID doesn't match that of the Org-Admin's parent account
        response = request_partial(INVALID_UUID, INVALID_UUID)
        self.validate_response(response, 302)   # Redirected to previous or user page

        # Publisher, logged in as Org-Admin, correct ORG-UUID provided, User-UUID is ignored because user is Org-Admin
        response = request_partial(self.publisher.uuid, INVALID_UUID)
        self.validate_response(response, 200)
        
        self.logout()

        # Login as Publisher Standard user
        self.login(self.pub_std_user.username, DEFAULT_PWD)
        
        # Publisher, logged in as Standard user, but requires user to be an Org-admin
        # (doesn't get as far as testing the User UUID)
        response = request_partial(self.publisher.uuid, INVALID_UUID)
        self.validate_response(response, 302)   # Redirected to previous or user page

        # Publisher, logged in as Standard user, but requires user to be an Org-admin
        response = request_partial(self.publisher.uuid, self.pub_std_user.uuid)
        self.validate_response(response, 302)   # Redirected to previous or user page
        
        self.logout()

        # Login as Publisher Read-only user
        self.login(self.pub_ro_user.username, DEFAULT_PWD)
        
        # Publisher, logged in as Read-only user, but requires user to be an Org-admin
        # (doesn't get as far as testing the User UUID)
        response = request_partial(self.publisher.uuid, INVALID_UUID)
        self.validate_response(response, 302)   # Redirected to previous or user page

        # Publisher, logged in as Read-only user, but requires user to be an Org-admin
        response = request_partial(self.publisher.uuid, self.pub_ro_user.uuid)
        self.validate_response(response, 302)   # Redirected to previous or user page
        
        self.logout()

        ## No need to test with Repository account users, as no difference ##


    def test_user_or_admin_org__gui_with_apikey(self):
        """
        THIS TESTING IS LIMITED by fact that by making request using api-key always returns the NON-Org-admin APIkey User,
        so CANNOT test all permutations e.g. those involving logging in as an Org-Admin for a Publisher or Repository Account.
        @return:
        """
        request_partial = partial(self.get_response_with_apikey_org_uuid_user_uuid, "security_gui.own_user_acc_or_org_admin_or_admin_org__gui")
        # Invalid API key
        response = request_partial(self.repository.uuid, self.repo_admin_user, INVALID_KEY)
        self.validate_response(response, 302)   # Redirected to Login page

        # Publisher, fails because ORG-UUID does not match the user's organisation
        response = request_partial(INVALID_UUID, self.pub_api_user.uuid, self.publisher.api_key)
        self.validate_response(response, 302)   # Redirected to previous or user page

        # Publisher, fails because USER-UUID does not match that of the API user.
        response = request_partial(self.publisher.uuid, INVALID_UUID, self.publisher.api_key)
        self.validate_response(response, 302)   # Redirected to previous or user page

        # Publisher
        response = request_partial(self.publisher.uuid, self.pub_api_user.uuid, self.publisher.api_key)
        self.validate_response(response, 200)

        ## DON'T need to test Repository accounts because same rules apply as for Publishers. ##

        # Admin (ignores UUID)
        response = request_partial(INVALID_UUID, INVALID_UUID, ADMIN_KEY)
        self.validate_response(response, 200)

    def test_user_or_admin_org__gui_with_login(self):
        """
        @return:
        """
        get_partial = partial(self.get_response_gui_uuid_user_uuid, "security_gui.own_user_acc_or_org_admin_or_admin_org__gui")
        post_partial = partial(self.post_response_gui_uuid_user_uuid, "security_gui.own_user_acc_or_org_admin_or_admin_org__gui")

        # Login as Admin Org (note that Admin accounts are automatically created outside of this file)
        self.login("admin", "admin")
        
        # Invalid ORG-UUID & USER-UUID - these are ignored because Org Ac is Admin
        response = get_partial(INVALID_UUID, INVALID_UUID)
        self.validate_response(response, 200)
        self.logout()

        # Login as Publisher Org-admin
        self.login(self.pub_admin_user.username, DEFAULT_PWD)
        
        # Publisher, logged in as Org-Admin, but provided ORG-UUID doesn't match that of the Org-Admin's parent account
        response = get_partial(INVALID_UUID, INVALID_UUID)
        self.validate_response(response, 302)   # Redirected to previous or user page

        # Publisher, logged in as Org-Admin, correct ORG-UUID provided, User-UUID is ignored because user is Org-Admin
        response = get_partial(self.publisher.uuid, INVALID_UUID)
        self.validate_response(response, 200)
        self.logout()

        # Login as Publisher Standard user
        self.login(self.pub_std_user.username, DEFAULT_PWD)
        
        # Publisher, logged in as Standard user, but wrong User UUID)
        response = get_partial(self.publisher.uuid, INVALID_UUID)
        self.validate_response(response, 302)   # Redirected to previous or user page

        # Publisher, logged in as Standard user, with correct User UUID
        response = get_partial(self.publisher.uuid, self.pub_std_user.uuid)
        self.validate_response(response, 200)

        response = post_partial(self.publisher.uuid, self.pub_std_user.uuid)
        self.validate_response(response, 200)

        self.logout()

        # Login as Publisher Read-only user
        self.login(self.pub_ro_user.username, DEFAULT_PWD)
        
        # Publisher, logged in as Read-only user, but requires user to be an Org-admin
        # (doesn't get as far as testing the User UUID)
        response = get_partial(self.publisher.uuid, INVALID_UUID)
        self.validate_response(response, 302)   # Redirected to previous or user page

        # Publisher, logged in as Read-only user with correct User UUID,
        response = get_partial(self.publisher.uuid, self.pub_ro_user.uuid)
        self.validate_response(response, 200)

        # Publisher, logged in as Read-only user with correct User UUID - FAILS as POST not allowed for Read-only user
        # Redirected to previous page
        response = post_partial(self.publisher.uuid, self.pub_ro_user.uuid)
        self.validate_response(response, 302)

        self.logout()

        ## No need to test with Repository account users, as no difference ##


    def test_org_user_or_admin_org_or_401__gui(self):
        get_partial = partial(self.get_response_gui_org_uuid, "security_gui.org_user_or_admin_org_or_401__gui")
        post_partial = partial(self.post_response_gui_org_uuid, "security_gui.org_user_or_admin_org_or_401__gui")

        # Login as Admin Org (note that Admin accounts are automatically created outside of this file)
        self.login("admin", "admin")

        # Invalid ORG-UUID & USER-UUID - these are ignored because Org Ac is Admin
        response = get_partial(INVALID_UUID)
        self.validate_response(response, 200)

        self.logout()

        # Login as Repo Org-admin

        self.login(self.repo_admin_user.username, DEFAULT_PWD)

        # Repo, logged in as Org-Admin, but provided ORG-UUID doesn't match that of the Org-Admin's parent account
        response = get_partial(INVALID_UUID)
        self.validate_response(response, 403)

        # Repo, logged in as Org-Admin, correct ORG-UUID provided, User-UUID is ignored because user is Org-Admin
        response = get_partial(self.repository.uuid)
        self.validate_response(response, 200)

        self.logout()

        # Login as Repo Standard user
        self.login(self.repo_std_user.username, DEFAULT_PWD)

        response = get_partial(self.repository.uuid)
        self.validate_response(response, 200)

        response = post_partial(self.repository.uuid)
        self.validate_response(response, 200)

        self.logout()

        # Login as Repo Read-only user
        self.login(self.repo_ro_user.username, DEFAULT_PWD)

        response = get_partial(self.repository.uuid)
        self.validate_response(response, 200)

        # POST fails, because user is Read-only
        response = post_partial(self.repository.uuid)
        self.validate_response(response, 403)

        self.logout()



    ## API Endpoints ##
    
    def test_api_authentication_required__api(self):
        login_required_partial = partial(self.get_response_with_apikey, "security_api.authentication_required__api")
        # Invalid key
        response = login_required_partial(INVALID_KEY)
        self.validate_response(response, 401)

        # Publisher
        response = login_required_partial(self.publisher.api_key)
        self.validate_response(response, 204)

        # Repository
        response = login_required_partial(self.repository.api_key)
        self.validate_response(response, 204)

        # Admin
        response = login_required_partial(ADMIN_KEY)
        self.validate_response(response, 204)

    def test_api_publisher_or_admin(self):
        publisher_or_admin_partial = partial(self.get_response_with_apikey, "security_api.publisher_or_admin_org__api")
        # Invalid key
        response = publisher_or_admin_partial(INVALID_KEY)
        self.validate_response(response, 401)

        # Publisher
        response = publisher_or_admin_partial(self.publisher.api_key)
        self.validate_response(response, 204)

        # Repository
        response = publisher_or_admin_partial(self.repository.api_key)
        self.validate_response(response, 403, ErrorMessages.FORBIDDEN_ERROR)

        # Admin
        response = publisher_or_admin_partial(ADMIN_KEY)
        self.validate_response(response, 204)

    def test_api_active_publisher_or_admin(self):
        active_pub_or_admin_partial = partial(
            self.get_response_with_apikey, "security_api.active_publisher_or_admin_org__api")
        # Invalid key
        response = active_pub_or_admin_partial(INVALID_KEY)
        self.validate_response(response, 401)

        # Inactive Publisher
        response = active_pub_or_admin_partial(self.publisher.api_key)
        self.validate_response(response, 403, ErrorMessages.DEACTIVATED_ACCOUNT_ERROR)

        # Publisher
        # Set the publisher status to suceeding
        self.publisher.publisher_data.toggle_status_on_off()
        self.publisher.update()

        response = active_pub_or_admin_partial(self.publisher.api_key)
        self.validate_response(response, 204)

        # Repository
        response = active_pub_or_admin_partial(self.repository.api_key)
        self.validate_response(response, 403, ErrorMessages.FORBIDDEN_ERROR)

        # Admin
        response = active_pub_or_admin_partial(ADMIN_KEY)
        self.validate_response(response, 204)
