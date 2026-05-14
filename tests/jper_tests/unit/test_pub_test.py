"""
Unit tests for the Publisher Automated Testing class
"""
from copy import deepcopy
from datetime import datetime
from time import sleep
from json import dumps
from octopus.lib.data import json_str_from_json_compressed_base64
from router.shared.models.note import RoutedNotification
from router.jper.app import app_decorator
from router.jper.models.publisher import PubTestRecord
from router.jper.api import JPER, ValidationException, ValidationMetaException
from router.jper.pub_testing import init_pub_testing, regex_check_creativecommons
from router.jper.validate_route import auto_testing_validation_n_routing, JISC_ORG_NAME_BEGINS
from tests.fixtures.factory import AccountFactory
from tests.jper_tests.fixtures.testcase import JPERTestCase
from tests.jper_tests.fixtures.api import APIFactory


class TestPubTest(JPERTestCase):
    @classmethod
    def setUpClass(cls):
        # List the tables (by table name) needed for testing
        cls.tables_for_testing = [
            'account', 'acc_user', 'notification', 'notification_account', 'pub_test', 'match_provenance'
        ]
        super().setUpClass()

    @app_decorator
    def setUp(self):
        # need to do this first, before kicking upstairs, as ESTestCase runs initialise
        super(TestPubTest, self).setUp()

    @app_decorator
    def tearDown(self):
        super(TestPubTest, self).tearDown()

    @staticmethod
    def create_pub_acc(live=True, in_test=False, test_type="u", route_note=False, no_default_licence=False):
        """
        Create publisher account.
        :param live: Boolean - True: Live account;  False: Test account
        :param in_test: Boolean - True: Auto-testing active;  False: No auto-testing
        :param test_type: String - "u" - Upon publication or "b" - Before publication
        :param route_note: Boolean - True: create & route a notification that passes auto-validation;
                                          False: Don't create/route notification (i.e. validate only)
        :param no_default_licence: Boolean - whether to set a default licence or not
        :return: publisher account object
        """
        if test_type not in ("u", "b"):
            raise Exception(f"Invalid publisher test type '{test_type}', should be one of: ['u', 'b']")
        publisher = AccountFactory.publisher_account(live)
        publisher.publisher_data.in_test = in_test
        pub_data = publisher.publisher_data
        pub_data.init_testing()
        pub_data.test_type = test_type
        if in_test:
            pub_data.test_start = "2020-10-10"
            pub_data.test_emails = ["pub_test@testing.com", "another@testing.com"]
            pub_data.route_note = route_note
        if no_default_licence:
            pub_data.license = {}

        # Set the publisher to be active
        publisher.status = 1
        publisher.update()
        # self.publisher_api_key = publisher.api_key
        return publisher

    @staticmethod
    def create_repo_acc(live=True, org_name="Repository account"):
        """
        Create repository account
        :param live:  Boolean - True: Live account;  False: Test account
        :param org_name: String  - Account org-name (if None then default will apply)
        :return: repo account object
        """
        repo_acc = AccountFactory.repo_account(live=live, save=False)
        repo_acc.org_name = "{} ({})".format(org_name, "live" if live else "test")
        repo_acc.insert()
        return repo_acc

    @app_decorator
    def test_01_account_statistics_and_test_records(self):
        """
        Check that test statistics are recorded on Publisher account when in active test mode; and also that
        PubTestRecords are created.
        """
        # 1. NOT active test mode - expect that PubTestRecord will NOT be created and pub-acc will NOT have its testing
        #    statistics updated.
        pub_acc = self.create_pub_acc(in_test=False, test_type="b")

        notification = APIFactory.incoming_notification_dict(provider_route="ftp", good_affs=True)
        del(notification["links"])  # Remove links to avoid generating an error
        del(notification["metadata"]["contributor"][0]["identifier"])     # Contributor identifier to force Issue generation

        pub_test = init_pub_testing(pub_acc, "api")
        recs_list_before = PubTestRecord.publisher_test_recs(publisher_id=pub_acc.id)
        # validation of notification will generate 1 issue, 0 error
        JPER.validate(pub_acc, notification, pub_test=pub_test)
        assert pub_test.num_issues() == 1
        assert pub_test.num_errors() == 0
        assert pub_test.compressed_json is not None

        pub_test.create_test_record_and_finalise_autotest()
        recs_list_after = PubTestRecord.publisher_test_recs(publisher_id=pub_acc.id)
        assert len(recs_list_before) == len(recs_list_after) == 0   # No PubTestRecord created
        test_stats_dict = pub_acc.publisher_data.testing_dict
        assert test_stats_dict["num_err"] == 0        # Account testing stats NOT updated
        assert test_stats_dict["num_ok"] == 0
        assert test_stats_dict["last"] is None
        assert test_stats_dict["last_ok"] is None
        assert test_stats_dict["last_err"] is None

        # 2. New publisher account, Active test mode - now expect both a PubTestRecord to be created and publisher
        #    account testing stats to be updated.
        pub_acc = self.create_pub_acc(in_test=True, test_type="b")
        pub_test= init_pub_testing(pub_acc, "api")

        recs_list_before = PubTestRecord.publisher_test_recs(publisher_id=pub_acc.id)
        # validation of notification will generate 3 issues, 0 errors
        JPER.validate(pub_acc, notification, pub_test=pub_test)
        assert pub_test.num_issues() == 1
        assert pub_test.num_errors() == 0
        pub_test.create_test_record_and_finalise_autotest()
        # Include JSON in query results
        recs_list_after = PubTestRecord.publisher_test_recs(publisher_id=pub_acc.id, with_json=True)
        test_stats_dict = pub_acc.publisher_data.testing_dict
        today_ymd = datetime.today().strftime("%Y-%m-%d")
        assert len(recs_list_before) + 1 == len(recs_list_after) == 1 

        pub_test_rec = recs_list_after[0]
        assert len(pub_test_rec.issues) == 1
        assert len(pub_test_rec.errors) == 0
        assert pub_test_rec.route == "api"
        assert pub_test_rec.doi == "10.pp/jit.1"
        assert pub_test_rec.filename is None
        assert pub_test_rec.valid
        assert pub_test_rec.json_comp is not None
        assert pub_test_rec.json_comp == pub_test.compressed_json
        assert json_str_from_json_compressed_base64(pub_test_rec.json_comp, sort_keys=True) == dumps(notification, sort_keys=True)
        assert test_stats_dict["num_err"] == 0
        assert test_stats_dict["num_ok"] == 1
        assert test_stats_dict["num_ok_since_err"] == 1
        assert test_stats_dict["last"] == today_ymd
        assert test_stats_dict["last_ok"] == today_ymd
        assert test_stats_dict["last_err"] is None

        # 3. Same publisher account - run another test, this time with validation errors - now expect both a
        #    PubTestRecord to be created and publisher account testing stats to be updated.
        sleep(1)    # Sleep 1 second so created date at least 1 sec later for new PubTestRecord
        notification = APIFactory.incoming_notification_dict(provider_route="ftp")
        del(notification["links"][0]["url"])   # This should generate "missing URL" error
        del(notification["links"][1]["url"])   # This should generate "missing URL" error
        pub_test.new_submission("test-filename")    # start a new submission

        with self.assertRaises(ValidationMetaException) as exc:
            JPER.validate(pub_acc, notification, pub_test=pub_test)
        assert "Validation: 2 errors & 2 issues found" == str(exc.exception)
        assert pub_test.num_issues() == 2
        assert pub_test.num_errors() == 2
        assert pub_test.compressed_json is not None
        assert dumps(notification, sort_keys=True) == json_str_from_json_compressed_base64(pub_test.compressed_json, sort_keys=True)
        pub_test.create_test_record_and_finalise_autotest()

        recs_list_after = PubTestRecord.publisher_test_recs(publisher_id=pub_acc.id)
        assert len(recs_list_after) == 2
        # Records are returned in creation date order, most recent first
        newest_rec = recs_list_after[0]
        assert len(newest_rec.issues) == 2
        assert len(newest_rec.errors) == 2
        assert newest_rec.route == "api"
        assert newest_rec.filename == "test-filename"
        assert not newest_rec.valid
        expected_errors = [
             '2 of the 2 supplied «links» had no URL',
             ('«metadata.author.affiliations» has missing fields:', ['«org»', '«country»', '«city»'])
        ]
        assert self.in_list_comparison(expected_errors, newest_rec.errors) is True
        assert newest_rec.json_comp is None     # By default, this value should be excluded from results of query
        test_stats_dict = pub_acc.publisher_data.testing_dict
        assert test_stats_dict["num_err"] == 1
        assert test_stats_dict["num_ok"] == 1
        assert test_stats_dict["num_ok_since_err"] == 0   # Has been reset since an error occurred
        assert test_stats_dict["last"] == today_ymd
        assert test_stats_dict["last_ok"] == today_ymd
        assert test_stats_dict["last_err"] == today_ymd


    @app_decorator
    def test_02_different_account_test_types_u_b(self):
        """
        Check that test rules vary as expected depending on whether accounts are set to test-type "u" (Upon Publication)
        or "b" (Before Publication).

        The following metadata requirements are different for "b"/"u":
        * metadata.journal.volume       b->desirable; u->mandatory
        * metadata.article.page_range   b->desirable; u->mandatory
        * metadata.publication_date.date b->desirable; u->mandatory
        * metadata.publication_date.year b->desirable; u->mandatory
        * metadata.publication_date.month b->desirable; u->mandatory
        * metadata.publication_date.day b->desirable; u->mandatory
        * metadata.license_ref.url     b->desirable; u->mandatory if publisher has NO default licence, otherwise optional
        """
        # --1-- "b" - Before publication (setting `in_test` to False - as this does NOT affect validation checks, but
        # only how results are logged and whether publisher account test stats are updated and PubTestRecord created.
        pub_acc = self.create_pub_acc(in_test=False, test_type="b")
        pub_test = init_pub_testing(pub_acc, "api")
        notification = APIFactory.incoming_notification_dict(good_affs=True, no_links=True)

        # Check initial number of issues/errors of notification with links removed
        # validation of notification will generate 2 issues, 0 error
        JPER.validate(pub_acc, notification, pub_test=pub_test)
        assert pub_test.num_errors() == 0
        assert pub_test.num_issues() == 0

        # Remove the metadata that is either desirable or mandatory
        del notification["metadata"]["journal"]["volume"]
        del notification["metadata"]["article"]["page_range"]
        del notification["metadata"]["article"]["e_num"]
        del notification["metadata"]["publication_date"]["date"]
        del notification["metadata"]["publication_date"]["year"]
        del notification["metadata"]["publication_date"]["month"]
        del notification["metadata"]["publication_date"]["day"]
        del notification["metadata"]["license_ref"][0]["url"]
        pub_test.new_submission()    # start a new submission
        JPER.validate(pub_acc, notification, pub_test=pub_test)
        assert pub_test.num_issues() == 4
        assert pub_test.num_errors() == 0

        expected_issues = [
            '«metadata.license_ref» has missing desirable field: «url»',
            '«metadata.journal.volume» is missing (desirable field)',
            '«metadata.article» has missing page information - either «page_range» or «e_num» (electronic location number) should be provided',
            # Because «date»', '«day»', '«year»', '«month»' are derived from dict keys, their order in the error message
            # can vary - hence the expected issue is specified as tuple, with tuple[0] being (unique) string that should
            # match one of the entries in the results list and tuple[1] being list of substrings that should also
            # appear in the result entry which was matched to tuple[0].
            ('«metadata.publication_date» has missing desirable fields: ', ['«date»', '«day»', '«year»', '«month»'])
        ]
        assert self.in_list_comparison(expected_issues, pub_test.issues) is True


        # --2-- Change Publisher account type to "u", re-run the validation - should get different results
        pub_acc.publisher_data.test_type = "u"
        pub_test = init_pub_testing(pub_acc, "api")         # Re-initialise to ensure modified account is used
        assert pub_test.pub_data.license.get("url")         # URL has a value
        assert pub_test.type == "u"
        with self.assertRaises(ValidationMetaException) as exc:
            JPER.validate(pub_acc, notification, pub_test=pub_test)
        assert "Validation: 3 errors & 0 issues found" == str(exc.exception)
        assert pub_test.num_issues() == 0
        assert pub_test.num_errors() == 3

        expected_errors = [
            '«metadata.journal.volume» is missing',
            '«metadata.article» has missing page information - either «page_range» or «e_num» (electronic location number) should be provided',
            # See comment above for explanation of this tuple
            ('«metadata.publication_date» has missing fields: ', ['«date»', '«day»', '«year»', '«month»'])
        ]
        assert self.in_list_comparison(expected_errors, pub_test.errors) is True

        # --3-- Change Publisher account (still type "u"), to remove the default licence and rerun validation
        pub_acc.publisher_data.license = None
        pub_test = init_pub_testing(pub_acc, "api")         # Re-initialise to ensure modified account is used
        assert pub_test.pub_data.license == {}
        assert pub_test.type == "u"
        with self.assertRaises(ValidationMetaException) as exc:
            JPER.validate(pub_acc, notification, pub_test=pub_test)
        assert "Validation: 4 errors & 0 issues found" == str(exc.exception)
        assert pub_test.num_issues() == 0
        assert pub_test.num_errors() == 4

        expected_errors = [
            '«metadata.license_ref» has missing field: «url»',
            '«metadata.journal.volume» is missing',
            '«metadata.article» has missing page information - either «page_range» or «e_num» (electronic location number) should be provided',
            # See earlier comment for explanation of this tuple
            ('«metadata.publication_date» has missing fields: ', ['«date»', '«day»', '«year»', '«month»'])
        ]
        assert self.in_list_comparison(expected_errors, pub_test.errors) is True


    @app_decorator
    def test_03_different_submission_paths_api_ftp(self):
        """
        Check that test rules vary as expected depending on whether source is set to "api" or "ftp".

        The following metadata requirements vary:
        * event     ftp->no validation, api->optional
        * metadata.article.language     ftp->desirable, api->mandatory
        * metadata.publication_status   ftp->no validation, api->mandatory
        """
        # --1-- Route: "ftp"
        pub_acc = self.create_pub_acc(in_test=False)
        notification = APIFactory.incoming_notification_dict(good_affs=True, no_links=True)

        # Remove the metadata under test that is either desirable or mandatory
        del notification["event"]
        del notification["metadata"]["article"]["language"]
        del notification["metadata"]["publication_status"]

        pub_test = init_pub_testing(pub_acc, "ftp")
        assert pub_test.route == "ftp"
        JPER.validate(pub_acc, notification, pub_test=pub_test)
        assert pub_test.num_issues() == 1
        assert pub_test.num_errors() == 0

        expected_issues = ['«metadata.article.language» is missing (desirable field)']
        assert self.in_list_comparison(expected_issues, pub_test.issues) is True

        # --2-- Route: "api", rerun test with same notification
        pub_test = init_pub_testing(pub_acc, "api")         # Re-initialise to ensure modified account is used
        assert pub_test.route == "api"
        with self.assertRaises(ValidationMetaException) as exc:
            JPER.validate(pub_acc, notification, pub_test=pub_test)
        assert "Validation: 2 errors & 0 issues found" == str(exc.exception)
        assert pub_test.num_issues() == 0
        assert pub_test.num_errors() == 2

        expected_errors = ['«metadata.article.language» is missing', '«metadata.publication_status» is missing']
        assert self.in_list_comparison(expected_errors, pub_test.errors) is True

        # --3-- Route: "api"  with bad publication status (which should be "Published" or "Accepted") and bad event
        notification["event"] = "Wrong-event"
        notification["metadata"]["article"]["language"] = ["en"]
        notification["metadata"]["publication_status"] = "Wrong-status"

        pub_test.new_submission()
        with self.assertRaises(ValidationMetaException) as exc:
            JPER.validate(pub_acc, notification, pub_test=pub_test)
        assert "Validation: 2 errors & 0 issues found" == str(exc.exception)
        assert pub_test.num_issues() == 0
        assert pub_test.num_errors() == 2
        expected_errors = [
            "«metadata.publication_status» has invalid value: 'Wrong-status' - allowed values are: ['Published', 'Accepted']",
            "«event» has invalid value: 'Wrong-event' - allowed values are: ['submitted', 'accepted', 'published', 'corrected', 'revised']"
        ]
        assert self.in_list_comparison(expected_errors, pub_test.errors) is True

        # Note that bad event and publication_status are NOT checked for FTP (because they are set by the system
        # so cannot be wrong)


    @app_decorator
    def test_04_autotest_create_and_route_notification(self):
        """
        Check that creation and routing of successfully validated notifications to Jisc Test repositories occurs
        if the "route_note" indicator is True.

        Variations to test:
            - route_note is True / False
            - Notifications validate with / without errors
            - Different repo accounts:
                 (i) Active test repo with Jisc in org-name
                 (ii) Inactive test repo with Jisc in org-name
                 (iii) Active Live repo with Jisc in org-name
                 (iv) Active test repo WITHOUT Jisc in org-name
        """
        in_note_dict = APIFactory.incoming_notification_dict(good_affs=True)
        # Remove source of potential issues/errors from base in_note_dict
        del in_note_dict["links"]

        pub_acc = self.create_pub_acc(in_test=True, route_note=True)
        repo_acc = self.create_repo_acc(live=False, org_name=f"{JISC_ORG_NAME_BEGINS} test repository")
        repo_acc_2 = self.create_repo_acc(live=False, org_name=f"Doesn't begin with {JISC_ORG_NAME_BEGINS} test repository")
        pub_test = init_pub_testing(pub_acc, "api")
        # --1-- Pub auto-testing, Successful notification, route_note is True, Active Jisc test repo a/c
        #       --> Notification IS created

        # Validate the incoming notification and route it
        note_id = auto_testing_validation_n_routing(pub_test, in_note_dict)
        assert pub_test.num_issues() == 0
        assert pub_test.num_errors() == 0
        assert note_id is not None
        routed_notification = RoutedNotification.pull(note_id)
        assert routed_notification is not None
        assert len(routed_notification.repositories) == 1
        assert routed_notification.repositories[0] == repo_acc.id


        # --2-- Pub auto-testing, Successful notification, route_note is False, Active Jisc test repo a/c
        #       --> Notification is NOT created

        # Change routing to False
        pub_acc.publisher_data.route_note = False
        pub_test = init_pub_testing(pub_acc, "api")

        # Validate the incoming notification, no routing should occur due to route_note being False
        note_id = auto_testing_validation_n_routing(pub_test, in_note_dict)
        assert pub_test.num_errors() == 0
        assert note_id is None


        # --3-- Pub auto-testing, Successful notification, route_note is True, NO Active Jisc test repo a/c
        #       --> Notification is NOT

        # Reset publisher account to route valid notifications
        pub_acc.publisher_data.route_note = True
        pub_test = init_pub_testing(pub_acc, "api")

        # De-activate Jisc repository account
        repo_acc.status = 0
        repo_acc.update()

        # Validate the incoming notification, no routing should occur due to Jisc repository acc now being "off"
        note_id = auto_testing_validation_n_routing(pub_test, in_note_dict)
        assert pub_test.num_errors() == 0
        assert note_id is None


        # --4-- Pub auto-testing, ERROR notification (metadata problem), route_note is True, Active Jisc test repo a/c
        #       --> Notification IS created even though ValidationMetaException is raised

        pub_test = init_pub_testing(pub_acc, "api")

        # Change Jisc repo-account back to active
        repo_acc.status = 1
        repo_acc.update()

        # Force incoming notification metadata error
        in_note_dict["metadata"]["publication_status"] = "BAD-status"

        num_routed_before = RoutedNotification.count()
        # Validate the incoming notification, Routing should occur despite metadata validation failure
        with self.assertRaises(ValidationMetaException) as exc:
            note_id = auto_testing_validation_n_routing(pub_test, in_note_dict)
        num_routed_after = RoutedNotification.count()

        assert note_id is None
        assert pub_test.num_errors() > 0
        assert self.in_list_comparison(
            ["«metadata.publication_status» has invalid value: 'BAD-status' - allowed values are: ['Published', 'Accepted']"],
            pub_test.errors
            ) is True
        # One routed notification record should have been added
        assert num_routed_before + 1 == num_routed_after

        # --5-- Pub auto-testing, ERROR notification (fatal metadata problem), route_note is True, Active Jisc test repo a/c
        #       --> Notification is NOT created

        pub_test = init_pub_testing(pub_acc, "api")

        # Reset incoming notification to be error-free
        in_note_dict["metadata"]["publication_status"] = "Published"
        # Force incoming notification metadata error
        in_note_dict["UNEXPECTED"] = "Invalid Field"

        num_routed_before = num_routed_after
        # Validate the incoming notification, Routing should NOT occur as ValidationException is raised (not
        # ValidationMetaException)
        with self.assertRaises(ValidationException) as exc:
            note_id = auto_testing_validation_n_routing(pub_test, in_note_dict)
        num_routed_after = RoutedNotification.count()
        assert note_id is None
        assert pub_test.num_errors() > 0
        assert self.in_list_comparison(
            ["Could not create Router record from supplied notification metadata: Field 'UNEXPECTED' is not permitted at 'root'"],
            pub_test.errors
            ) is True
        # No new notification record should have been added
        assert num_routed_before == num_routed_after

        # --6-- Pub NOT auto-testing, Successful notification, route_note is True, Active Jisc test repo a/c
        #       --> Notification is NOT created

        # Reset publisher account to be NOT auto-testing
        pub_acc.publisher_data.in_test = False
        pub_test = init_pub_testing(pub_acc, "api")

        # Reset incoming notification to be error-free by removing unexpected field
        del(in_note_dict["UNEXPECTED"])

        # Validate the incoming notification, no routing should occur due to Account NOT in auto-test mode
        note_id = auto_testing_validation_n_routing(pub_test, in_note_dict)
        assert pub_test.num_errors() == 0
        assert note_id is None


        # --7   --> Notification is NOT created

        # Reset publisher to be actively testing & routing valid notifications
        pub_acc.publisher_data.in_test = True
        pub_acc.publisher_data.route_note = True
        pub_test = init_pub_testing(pub_acc, "api")

        # Repo account no longer has "Jisc" in org-name
        repo_acc.org_name = "Random Organisation Name"
        repo_acc.update()

        # Validate the incoming notification, no routing should occur due to NO repository with Jisc in org-name
        note_id = auto_testing_validation_n_routing(pub_test, in_note_dict)
        assert pub_test.num_errors() == 0
        assert note_id is None


        # --8-- Pub auto-testing, Successful notification, route_note is True, Active Jisc Live repo a/c
        #       --> Notification is NOT created
        pub_test = init_pub_testing(pub_acc, "api")

        # "Jisc" Repo account is now Live
        repo_acc.org_name = f"{JISC_ORG_NAME_BEGINS} Live Account"
        repo_acc.live_date = "2020-01-01T12:12:12Z"
        repo_acc.update()

        # Validate the incoming notification, no routing should occur due to Jisc repo Account being Live
        note_id = auto_testing_validation_n_routing(pub_test, in_note_dict)
        assert pub_test.num_errors() == 0
        assert note_id is None


    @app_decorator
    def test_05_miscellaneous_cases(self):
        """
        Check that test rules work for particular cases:
            * many problems
            * bad article version
            * page_range provided, but start_page / end_page missing
            * bad author type e.g. type: "noddy"
            * irregular author type e.g. type: "an-author"
        """
        pub_acc = self.create_pub_acc(in_test=False)
        pub_test = init_pub_testing(pub_acc, "ftp")
        assert pub_test.route == "ftp"

        # --1-- Many errors & issues
        notification = APIFactory.incoming_notification_dict(bad=True)
        with self.assertRaises(ValidationException) as exc:
            JPER.validate(pub_acc, notification, pub_test=pub_test)

        assert pub_test.num_errors() == 23
        assert pub_test.num_issues() == 8
        expected_errors = [
            "«metadata.contributor» has empty field: «type» among the array elements",
            "«metadata.contributor.name» has empty field: «surname» among the array elements",
            "In «metadata.license_ref.start» an invalid date '01-01-2015' was found (required format is: YYYY-MM-DD)",
            "A licence «start» date is required for all but one of the «metadata.license_ref» elements (1 were found in 3 licences)",
            "«metadata.funding» has missing field: «name» among the array elements",
            "«metadata.journal.title» is missing",
            "«metadata.journal.identifier» has missing field: «id»",
            "«metadata.article.title» is empty",
            "«metadata.article.version» is empty",
            "«metadata.article.identifier» has empty field: «id» among the array elements",
            "The «metadata.article.identifier» array had 2 DOIs, but only 1 is allowed",
            "«metadata.author» has missing field: «affiliations»; & empty field: «affiliations» among the array elements",
            ('«metadata.author.affiliations» has missing fields:', ['«org»', '«country»', '«city»']),
            "«metadata.author.type» has invalid value: 'BAD' among the array elements - allowed values are: ['author', 'corresp']",
            "«metadata.author.name» has missing field: «firstname»; & empty field: «surname»; & unexpected field: «oops-name» among the array elements",
            ('«metadata.author.identifier» has missing fields: ', ['«type»', '«id»', '; & empty field: «id»; & unexpected field: «oops-id» among the array elements']),
            "In «metadata.accepted_date» an invalid date '01-09-2014' was found (required format is: YYYY-MM-DD)",
            "«metadata.journal.volume» is missing",
            "In «metadata.publication_date» the «Year» field value '2014' did not match the «date» field part '2015' (required format is YYYY)",
            "«metadata.publication_date.publication_format» has invalid value: 'BAD' - allowed values are: ['electronic', 'printed', 'print']",
            "In «metadata.publication_date» the «Month» field value '' did not match the «date» field part '01' (required format is MM)",
            "«metadata.publication_date» has empty field: «month»",
            "Could not create Router record from supplied notification metadata: Field 'oops-name' is not permitted at 'metadata.author[0].name.'"
        ]
        assert self.in_list_comparison(expected_errors, pub_test.errors) is True

        expected_issues = [
            "«metadata.contributor» has missing desirable field: «identifier»",
           ('«metadata.contributor.affiliations» has missing desirable fields', ["org", "identifier"]),
            "«metadata.article.subject» is empty",
            "In «metadata.license_ref» a non-creativecommons licence URL 'url' appears",
            '«metadata.ack» is missing (desirable field)',
            "In the «metadata.author» array, 2 of the 3 authors have an ORCID specified",
            ('«metadata.author.affiliations» has missing desirable fields', ["street", "postcode", "identifier", "dept", "country_code"]),
            '«metadata.article.start_page» is missing (desirable field)'
        ]
        assert self.in_list_comparison(expected_issues, pub_test.issues) is True

        # --2-- Bad article versions
        notification = APIFactory.incoming_notification_dict(good_affs=True, no_links=True)
        # Set test data
        notification["metadata"]["article"]["version"] = "BAD"

        pub_test.new_submission()
        with self.assertRaises(ValidationMetaException) as exc:
            JPER.validate(pub_acc, notification, pub_test=pub_test)
        assert pub_test.num_errors() == 1
        assert "«metadata.article.version» has invalid value: 'BAD' - allowed values are: ['AM', 'P', 'VOR', 'EVOR', 'CVOR', 'C/EVOR']" == pub_test.errors[0]

        # --3-- For API submissions page_range provided, but start_page & end_page are absent
        notification = APIFactory.incoming_notification_dict(provider_route="api", good_affs=True, no_links=True)
        # Set test data
        del notification["metadata"]["article"]["start_page"]
        del notification["metadata"]["article"]["end_page"]
        pub_test.new_submission()
        JPER.validate(pub_acc, notification, pub_test=pub_test)

        assert pub_test.num_errors() == 0
        assert pub_test.num_issues() == 2
        assert self.in_list_comparison(
            ['«metadata.article.start_page» is missing (desirable field)',
             '«metadata.article.end_page» is missing (desirable field)'],
            pub_test.issues
            ) is True

        # --4-- All authors missing identifiers
        notification = APIFactory.incoming_notification_dict(no_links=True, remove_auth_id="all")
        pub_test.new_submission()
        with self.assertRaises(ValidationMetaException) as exc:
            JPER.validate(pub_acc, notification, pub_test=pub_test)

        assert pub_test.num_errors() == 2
        assert self.in_list_comparison(
            ['In the «metadata.author» array, 0 of the 2 authors has an ORCID specified (in an «identifier» element); at least one and ideally all authors should have an ORCID specified',
             ('«metadata.author.affiliations» has missing fields:', ['«org»', '«country»', '«city»'])],
            pub_test.errors) is True
        assert pub_test.num_issues() == 3
        assert self.in_list_comparison(
            [
                '«metadata.author» has missing desirable field: «identifier» among the array elements',
                ('«metadata.contributor.affiliations» has missing desirable fields:', ['«identifier»', '«org»', '«country»', '«city»', '«street»', '«postcode»']),
                ('«metadata.author.affiliations» has missing desirable fields:', ['«identifier»', '«street»', '«postcode»'])
            ],
            pub_test.issues) is True

        # --5-- No author ORCIDS (although other identifiers present)
        notification = APIFactory.incoming_notification_dict(no_links=True, remove_auth_id="orcid")
        pub_test.new_submission()
        with self.assertRaises(ValidationMetaException) as exc:
            JPER.validate(pub_acc, notification, pub_test=pub_test)

        assert pub_test.num_errors() == 2
        assert self.in_list_comparison(
            ['In the «metadata.author» array, 0 of the 2 authors has an ORCID specified (in an «identifier» element); at least one and ideally all authors should have an ORCID specified',
             ('«metadata.author.affiliations» has missing fields:', ['«org»', '«country»', '«city»'])],
            pub_test.errors) is True
        assert pub_test.num_issues() == 2
        assert self.in_list_comparison(
            [
                ('«metadata.contributor.affiliations» has missing desirable fields:', ['«identifier»', '«org»', '«country»', '«city»', '«street»', '«postcode»']),
                ('«metadata.author.affiliations» has missing desirable fields:', ['«identifier»', '«street»', '«postcode»'])
            ],
            pub_test.issues) is True

        # --6-- Bad author type should generate error
        notification = APIFactory.incoming_notification_dict(good_affs=True, no_links=True, set_auth_type="BAD")
        # notification["metadata"]["license_ref"][0]["url"] = "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
        pub_test.new_submission()
        with self.assertRaises(ValidationMetaException) as exc:
            JPER.validate(pub_acc, notification, pub_test=pub_test)

        assert pub_test.num_errors() == 2
        assert self.in_list_comparison(
            [
                "The list of «metadata.author» objects must include one with a «type» value of 'corresp' (indicating corresponding author)",
                ("«metadata.author.type» has invalid values: ",
                 ["BAD-1", "BAD-2", "among the array elements - allowed values are: ['author', 'corresp']"]
                 )
            ],
            pub_test.errors) is True

        # --7-- Irregular author type should generate issue
        notification = APIFactory.incoming_notification_dict(good_affs=True, no_links=True, set_auth_type="an-author")
        # notification["metadata"]["license_ref"][0]["url"] = "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
        pub_test.new_submission()
        with self.assertRaises(ValidationMetaException) as exc:
            JPER.validate(pub_acc, notification, pub_test=pub_test)

        assert pub_test.num_errors() == 1
        assert pub_test.num_issues() == 1
        assert pub_test.errors[0] == "The list of «metadata.author» objects must include one with a «type» value of 'corresp' (indicating corresponding author)"
        assert self.in_list_comparison(
            [("«metadata.author.type» has irregular values: ",
              ["an-author-1", "an-author-2", "among the array elements - preferred values are: ['author', 'corresp']"])
             ],
            pub_test.issues) is True


    @app_decorator
    def test_06_auth_affiliations(self):
        """
        Check that author affiliation issues are identified
        :return:
        """
        pub_acc = self.create_pub_acc(in_test=False)
        pub_test = init_pub_testing(pub_acc, "ftp")

        # --1-- Some Affiliations are missing required structured elements
        notification = APIFactory.incoming_notification_dict(no_links=True)
        pub_test.new_submission()
        with self.assertRaises(ValidationMetaException) as exc:
            JPER.validate(pub_acc, notification, pub_test=pub_test)

        assert pub_test.num_errors() == 1
        assert self.in_list_comparison(
            [('«metadata.author.affiliations» has missing fields:', ['«org»', '«country»', '«city»'])],
            pub_test.errors) is True
        assert pub_test.num_issues() == 2
        assert self.in_list_comparison(
            [
                ('«metadata.contributor.affiliations» has missing desirable fields:', ['«identifier»', '«org»', '«country»', '«city»', '«street»', '«postcode»']),
                ('«metadata.author.affiliations» has missing desirable fields:', ['«identifier»', '«street»', '«postcode»'])
            ],
            pub_test.issues) is True

        # --2-- Various problematic <org> values
        problem_org_values = [
            "Bangor University, 123 Senate Ave, Bangor, Wales",
            "Philosophy Department, Cardiff University",
            "St. John's College, University of Oxford ",
            "Cambridge University, Kings College",
            "Faculty of Education, Manchester University",
            "Madchester College, also at Manchester",
            "Bendix Building, Brighton University",
            "Rat laboratory, Liverpool University",
            "Professor Brainstorm, Exeter University",
            "Unit 13, Somewhere",
            "Dog dept, Bath University"
        ]
        auths = notification["metadata"]["author"]
        base_auth = deepcopy(auths[0])
        for x, org in enumerate(problem_org_values):
            new_auth = deepcopy(base_auth)
            new_auth["type"] = "author"
            new_name = new_auth["name"]
            new_name["firstname"] += f"-{x}"
            new_name["surname"] += f"-{x}"
            new_name["fullname"] = new_name["firstname"] + " " + new_name["surname"]
            new_auth["affiliations"][0]["org"] = org
            auths.append(new_auth)

        pub_test.new_submission()
        with self.assertRaises(ValidationMetaException) as exc:
            JPER.validate(pub_acc, notification, pub_test=pub_test)
        assert pub_test.num_issues() == 14
        assert self.in_list_comparison(
            [
                '«metadata.author.affiliations.org» may be overpopulated: "St. John\'s College, University of Oxford" (contains "University" & "College")',
                '«metadata.author.affiliations.org» may be overpopulated: "Bangor University, 123 Senate Ave, Bangor, Wales" (contains more than 1 comma)',
                '«metadata.author.affiliations.org» may be overpopulated: "Bendix Building, Brighton University" (contains "Building")',
                '«metadata.author.affiliations.org» may be overpopulated: "Faculty of Education, Manchester University" (contains "Faculty")',
                '«metadata.author.affiliations.org» may be overpopulated: "Philosophy Department, Cardiff University" (contains "Department")',
                '«metadata.author.affiliations.org» may be overpopulated: "Rat laboratory, Liverpool University" (contains "laboratory")',
                '«metadata.author.affiliations.org» may be overpopulated: "Professor Brainstorm, Exeter University" (contains "Professor")',
                '«metadata.author.affiliations.org» may be overpopulated: "Unit 13, Somewhere" (contains "Unit")',
                '«metadata.author.affiliations.org» may be overpopulated: "Madchester College, also at Manchester" (contains "also at")',
                '«metadata.author.affiliations.org» may be overpopulated: "Dog dept, Bath University" (contains "dept")',
                '«metadata.author.affiliations.org» may be overpopulated: "Cambridge University, Kings College" (contains "University" & "College")',
                'In the «metadata.author» array, 11 of the 25 affiliations (from 13 authors) have «org» values that may contain more than the institution name. Affiliation address elements, including department & organisation names, should each be tagged separately',
                ('«metadata.contributor.affiliations» has missing desirable fields:', ['«identifier»', '«org»', '«country»', '«city»', '«street»', '«postcode»']),
                ('«metadata.author.affiliations» has missing desirable fields:', ['«dept»', '«identifier»', '«street»', '«postcode»', '«country_code»'])
            ],
            pub_test.issues) is True


    @app_decorator
    def test_07_licence_n_embargo(self):
        """
        Check that licence & embargo errors/issues are properly reported
        :return:
        """
        pub_acc = self.create_pub_acc(in_test=False)
        pub_test = init_pub_testing(pub_acc, "ftp")

        # --1-- Default licence applied
        # pub_acc = self.create_pub_acc(in_test=False, no_default_licence=True)
        notification = APIFactory.incoming_notification_dict(good_affs=True, no_links=True)
        # Set test data
        del notification["metadata"]["license_ref"]
        del notification["metadata"]["embargo"]

        pub_test.new_submission()
        JPER.validate(pub_acc, notification, pub_test=pub_test)
        assert pub_test.num_issues() == 2
        assert self.in_list_comparison(
            ['No licence in metadata, but publisher default licence was applied with start date',
             "In «metadata.license_ref» a non-creativecommons licence URL 'https://default.sagepub.com/default' appears - may be OK if intentional"             ],
            pub_test.issues
            ) is True

        # --2-- Default licence applied, when NO publication date
        notification = APIFactory.incoming_notification_dict(good_affs=True, no_links=True)
        # Set test data
        del notification["metadata"]["license_ref"]
        del notification["metadata"]["embargo"]
        del notification["metadata"]["publication_date"]
        pub_test.new_submission()
        with self.assertRaises(ValidationMetaException) as exc:
            JPER.validate(pub_acc, notification, pub_test=pub_test)

        assert "Validation: 1 error & 1 issue found" == str(exc.exception)
        assert pub_test.num_errors() == 1
        assert pub_test.num_issues() == 1
        assert self.in_list_comparison(
            ["No licence in metadata, but 'under embargo (end date unknown)' licence text applied"
             ],
            pub_test.issues
            ) is True

        # --3-- For API submissions when NO licence, but FUTURE embargo exists - Licence message added
        notification = APIFactory.incoming_notification_dict(provider_route="api", good_affs=True, no_links=True)
        # Set test data
        del notification["metadata"]["license_ref"]
        today_ymd = datetime.today().strftime("%Y-%m-%d")
        next_year = int(today_ymd[:4]) + 1
        notification["metadata"]["embargo"]["end"] = str(next_year) + today_ymd[4:]
        pub_test.new_submission()
        with self.assertRaises(ValidationMetaException) as exc:
            JPER.validate(pub_acc, notification, pub_test=pub_test)

        assert "Validation: 1 error & 0 issues found" == str(exc.exception)
        assert pub_test.num_errors() == 1
        assert pub_test.num_issues() == 0
        assert "No licence in metadata, although an embargo is provided" == pub_test.errors[0]

        # --4-- For API submissions with publication date when NO licence, but Embargo duration provided
        notification = APIFactory.incoming_notification_dict(provider_route="api", good_affs=True, no_links=True)
        # Set test data
        del notification["metadata"]["license_ref"]
        del notification["metadata"]["embargo"]["end"]
        pub_test.new_submission()
        with self.assertRaises(ValidationMetaException) as exc:
            JPER.validate(pub_acc, notification, pub_test=pub_test)

        assert "Validation: 1 error & 0 issues found" == str(exc.exception)
        assert pub_test.num_errors() == 1
        assert pub_test.num_issues() == 0
        assert "No licence in metadata, although embargo duration is provided (embargo end date derived from publication date)" == pub_test.errors[0]

        # --5-- For API submissions when NO publication date & NO licence, but Embargo duration provided
        notification = APIFactory.incoming_notification_dict(provider_route="api", good_affs=True, no_links=True)
        # Set test data
        del notification["metadata"]["publication_date"]
        del notification["metadata"]["license_ref"]
        del notification["metadata"]["embargo"]["end"]
        pub_test.new_submission()
        with self.assertRaises(ValidationMetaException) as exc:
            JPER.validate(pub_acc, notification, pub_test=pub_test)

        assert "Validation: 2 errors & 0 issues found" == str(exc.exception)
        assert pub_test.num_errors() == 2
        assert pub_test.num_issues() == 0
        assert "No licence in metadata, although an embargo duration is provided" == pub_test.errors[0]

        # --6-- Open licence should not generate issue
        notification = APIFactory.incoming_notification_dict(good_affs=True, no_links=True)
        notification["metadata"]["license_ref"][0]["url"] = "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
        pub_test.new_submission()
        JPER.validate(pub_acc, notification, pub_test=pub_test)
        assert pub_test.num_issues() == 0

        # --7-- For API submissions with publication date when NO licence provided
        pub_acc.publisher_data.license = None
        notification = APIFactory.incoming_notification_dict(provider_route="api", good_affs=True, no_links=True)
        # Set test data
        del notification["metadata"]["license_ref"]
        del notification["metadata"]["embargo"]
        pub_test.new_submission()
        with self.assertRaises(ValidationMetaException) as exc:
            JPER.validate(pub_acc, notification, pub_test=pub_test)

        assert "Validation: 1 error & 0 issues found" == str(exc.exception)
        assert pub_test.num_errors() == 1
        assert pub_test.num_issues() == 0
        assert "«metadata.license_ref» is empty" == pub_test.errors[0]


    @app_decorator
    def test_08_cc_urls(self):
        """
        Check that expected CC URL patterns are all accepted; and conversely that illegal CC URLS will be rejected.
        :return:
        """
        ok_cc_urls = (
            "https://creativecommons.org/licenses/by/{}.0/legalcode",
            "https://creativecommons.org/licenses/by/{}.0/",
            "https://creativecommons.org/licenses/by/{}.0",
            "https://creativecommons.org/licenses/by-nc/{}.0/",
            "http://creativecommons.org/licenses/by-sa/{}.0/",
            "http://creativecommons.org/licenses/by-nc-sa/{}.0/",
            "http://creativecommons.org/licenses/by-nd/{}.0/",
            "http://creativecommons.org/licenses/by-nc-nd/{}.0/legalcode",
            "http://creativecommons.org/licenses/by-nc-nd/{}.0/",
            "http://creativecommons.org/licenses/by-nc-nd/{}.0",
        )
        for url in ok_cc_urls:
            for num in (1, 2, 3, 4):
                assert regex_check_creativecommons.match(url.format(num)) is not None

        ok_cc_urls_publicdomain = (
            "https://creativecommons.org/publicdomain/zero/1.0/",
            "https://creativecommons.org/publicdomain/zero/1.0",
            "https://creativecommons.org/publicdomain/zero/1.0/legalcode",
            "http://creativecommons.org/publicdomain/zero/1.0/",
            "http://creativecommons.org/publicdomain/zero/1.0",
            "http://creativecommons.org/publicdomain/zero/1.0/legalcode"
        )

        for url in ok_cc_urls_publicdomain:
            assert regex_check_creativecommons.match(url) is not None

        bad_cc_urls = (
            "https://creativecommons.org/licenses/by/{}.0/code",
            "https://creativecommons.com/licenses/by/{}.0/legalcode",
            "https://creativecommons.org/licenses/nc/{}.0/",
            "https://creativecommons.org/licenses/bye/{}.0",
            "https://creativecommons.org/licences/by-nc/{}.0/",
            "creativecommons.org/licenses/by-sa/{}.0/",
            "https://creativecommons.org/licenses/nd-by/{}.0/",
            "https://creativecommons.org/licenses/by-nd-nc/{}.0/",
            "https://creativecommons.org/licenses/by-nd-nc/{}/",
        )
        for url in bad_cc_urls:
            assert regex_check_creativecommons.match(url.format(4)) is None
