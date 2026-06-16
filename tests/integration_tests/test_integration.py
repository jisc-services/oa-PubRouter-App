
import csv
import time
import os
from flask import current_app
from datetime import datetime, date, timezone
from dateutil.relativedelta import relativedelta
from octopus.lib.data import list_get
from octopus.lib.paths import get_real_path
from octopus.modules.logger.test_helper import LoggingBufferContext
from router.shared.mysql_db_ddl import JPER_REPORTS_TABLES
from router.shared.models.note import RoutedNotification, UnroutedNotification
from router.jper.scheduler import check_unrouted, check_harvested_unrouted, processftp
from router.jper import reports
from router.jper.models.publisher import FTPDepositRecord
from router.jper.models.repository import MatchProvenance
from router.jper.models.reports import MonthlyInstitutionStats, MonthlyPublisherStats
from router.harvester.harvester_main import Harvester, StandardGracefulKiller
from tests.harvester_tests.fixtures.harvester_utils import HarvesterTestUtils
from tests.harvester_tests.fixtures.test_data import epmc_json_dict
from tests.fixtures.factory import AccountFactory
from tests.jper_tests.fixtures.models import IdentifierFactory
from tests.jper_tests.fixtures.testcase import JPERTestCase, app_decorator
from tests.jper_tests.fixtures.packages import PackageFactory


def get_path_with_file(*args):
    return get_real_path(__file__, *args)


def make_custom_zip(pub_id, zip_name="custom.zip", inc_pdf=True):
    ftp_dir = get_path_with_file(current_app.config.get("FTP_TMP_DIR", ""), str(pub_id), "xfer")
    if not os.path.exists(ftp_dir):
        os.makedirs(ftp_dir)
    xfer_file = os.path.join(ftp_dir, zip_name)
    PackageFactory.make_custom_zip(xfer_file, inc_pdf=inc_pdf)


def month_num_to_string(num):
    month_list = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    is_good_num = 1 <= num <= 12
    return list_get(month_list, num - 1) if is_good_num else None


class TestIntegration(JPERTestCase):
    """
    Integration tests for Router.

    These test the entire app 1 routing process. So, the process of creating notifications from router.harvester/ftp, then
        matching notifications to repositories.

    There is also a test to create the CSV report.
    """

    @classmethod
    def setUpClass(cls):
        # List the tables (by table name) needed for testing
        cls.tables_for_testing = ['account', 'acc_user', 'acc_notes_emails', 'acc_repo_match_params', 'notification', 'notification_account',
                                  'match_provenance', 'pub_deposit', 'metrics', 'harvested_unrouted', 'doi_register',
                                  'org_identifiers', 'h_webservice', 'h_errors', 'h_history']

        super(TestIntegration, cls).setUpClass()
        cls.db.create_tables(JPER_REPORTS_TABLES)

    def setUp(self):
        super(TestIntegration, self).setUp()
        self.db.truncate_tables(list(JPER_REPORTS_TABLES.keys()))
        print("-- Truncated reports tables")

    @app_decorator
    def test_01_harvester_integration(self):
        """
        Does the following process:
            * Creates Unrouted harvested notifications
            * Creates two accounts, a live repo account and a live repo account that is off, both with matching parameters
            * Runs the matching process.
        A successful test result is that only the live repo account that is not off is matched with the document.
        """
        Harvester.killer = StandardGracefulKiller(current_app.logger)

        def mock_hits_from_es(json_data_dict, id="1"):
            doc = {
                '_source': json_data_dict,
                '_id': id
            }
            return [doc]

        def query_engine(harvester_id):
            from router.harvester.engine.GetEngine import get_harvester_engine
            return get_harvester_engine(
                current_app.config["EPMC"],
                HarvesterTestUtils.es_conn(),
                current_app.config["WEBSERVICES_DATA_EPMC"]['url'],
                harvester_id,
                datetime.today(),
                datetime.today(),
                current_app.config["EPMC"]
            )

        ### Create an unrouted notification for an EPMC notification harvested by a "Live" EPMC webservice ###
        # Create Live Harvester webservice
        live_epmc_ws_id = HarvesterTestUtils.create_live_epmc_ws_record()

        # Create EPMC query engine
        live_epmc_engine = query_engine(live_epmc_ws_id)

        # Mock hits as if retrieved from ES database, with ID of 1
        epmc_hits = mock_hits_from_es(epmc_json_dict, '1')

        Harvester.provider_id = live_epmc_ws_id
        unrouted_saved, success = Harvester.create_unrouted_notifications(epmc_hits, live_epmc_engine)
        assert unrouted_saved == 1
        assert success

        ### Create and send to Router an EPMC notification harvested by a "Test" EPMC webservice ###
        # Create Test Harvester webservice
        test_epmc_ws_id = HarvesterTestUtils.create_test_epmc_ws_record()

        # Create EPMC query engine
        test_epmc_engine = query_engine(test_epmc_ws_id)

        # Mock hits as if retrieved from ES database, with ID of 2
        epmc_hits = mock_hits_from_es(epmc_json_dict, '2')
        Harvester.provider_id = test_epmc_ws_id
        unrouted_saved, success = Harvester.create_unrouted_notifications(epmc_hits, test_epmc_engine)
        assert unrouted_saved == 1
        assert success

        # Create live repo account with repo config that matches any routed notification from a Live harvester
        live_repo = AccountFactory.repo_account(live=True)
        AccountFactory.add_config(live_repo)        # This updates (saves) the account

        # Make Live "off" repo account that should not be used during the matching (since it is Off)
        live_off_repo = AccountFactory.repo_account(live=True)
        live_off_repo.repository_data.repository_off()
        AccountFactory.add_config(live_off_repo)    # This updates (saves) the account

        # Create test repo account with repo config that matches any routed notification
        test_repo = AccountFactory.repo_account(live=False)
        AccountFactory.add_config(test_repo)  # This updates (saves) the account

        # Make test "off" repo account that should not be used during the matching (since it is Off)
        test_off_repo = AccountFactory.repo_account(live=False)
        test_off_repo.repository_data.repository_off()
        AccountFactory.add_config(test_off_repo)  # This updates (saves) the account

        # Run check_unrouted process
        check_harvested_unrouted()
        ## We expect that the 2 notifications (1 from Live and 1 from Test harvester) will be routed as follows:
        #   - Live notification -> 2 repositories (live_repo, test_repo)
        #   - Test notification -> 1 repo (test_repo)
        # Hence we expect 3 match provenance records

        # Get list of routed notifications
        routed_list = RoutedNotification.list_routed()

        assert len(routed_list) == 2
        assert MatchProvenance.count(pull_name="all") == 3
        assert len(FTPDepositRecord.get_all()) == 0
        for es_note in routed_list:
            harvester_id = es_note.provider_harv_id
            repos = es_note.repositories
            # If notification from Live source, it should be matched to 2 repositories
            if harvester_id == live_epmc_ws_id:
                assert len(repos) == 2
                assert live_repo.id in repos
                assert test_repo.id in repos
            # Else from Test source, it should have been matched to 1 repo
            elif harvester_id == test_epmc_ws_id:
                assert len(repos) == 1
                assert test_repo.id in repos
            else:
                assert False

    @app_decorator
    def test_02_zip_integration(self):
        """
        Does the following process:
            * Creates a publisher account
            * Creates a valid zip file for FTP submissions
            * Processes the zip file
            * Creates two accounts, a live repo account and a live repo account that is off
            * Does the matching process
            * Checks whether a valid FTP record has been created
            * Checks that only the live repo account that is not off has been matched.

        A successful result should have an FTP record relevant to the created publisher, it should be successful
            and matched.
        It should also only match to the live repo account that is not off.
        """
        # Create test publisher and make zip file in correct folder
        pub = AccountFactory.publisher_account()
        make_custom_zip(pub.uuid, inc_pdf=False)
        # processftp to make unrouted
        processftp()

        repo = AccountFactory.repo_account(live=True)
        # Add config that has a max_pub_age set - this is so it makes sure FTP works with max_pub_age
        AccountFactory.add_config(repo)
        # Make off account to make sure it also doesn't match accounts that are off
        off_acc = AccountFactory.repo_account(live=True, save=False)
        off_acc.repository_data.repository_off()
        off_acc.insert()

        log_context = LoggingBufferContext(close_on_exit=True, logger_=current_app.logger)
        with log_context:
            # Run check_unrouted
            check_unrouted()
            assert log_context.msg_in_buffer(
                "ERROR_X: route: No PDF file was found in the submitted zip file")

        records = FTPDepositRecord.get_all()
        assert len(records) > 0
        record = records[0]
        assert record.publisher_id == pub.id
        assert record.successful
        assert record.matched
        assert record.matched_live
        assert MatchProvenance.count() == 1
        assert RoutedNotification.count() == 1

    @app_decorator
    def test_03_institution_and_pub_doi_report_integration(self):
        """
        Tests 3 reports:
            - Live Institution report
            - Test Institution report
            - Publisher DOI report (which is created from Routed Notifications)

        Does the following process:
            * Creates a publisher account to create ftp submissions for.
            * Creates a live repo account which started at the start of the month, and an identifier which it can use.
            * Creates an account that became live sometime during the month, but starts it as test.
            * Creates a test account.
            * Creates 10 zip files that match to all three repos.
            * Sets the account that became live during the month to actually be live.
            * Creates another 10 zip files that match to all three repos.
            * Runs the report process (for institutions).

            * Create Publisher DOI matched to institution reports
            * Check report values are as expected
        A successful result will have two repos in each file, with the live_through_month_account being in both.
        The test and live repo accounts will both match 20 notifications.
        The live through month account will match 10 in the test file, and 10 in the live file.
        The live repo account will have a Jisc ID with a given id.
        """
        # Create test accounts
        pub_one = AccountFactory.publisher_account()
        pub_one.org_name = "TestPublisher1"
        pub_one.update()

        pub_two = AccountFactory.publisher_account()
        pub_two.org_name = "TestPublisher2"
        pub_two.data["api_key"] = "other_pub_key"
        pub_two.publisher_data.report_format = "B"  # One row per institution, blank out repeated values
        pub_two.update()

        test_acc = AccountFactory.repo_account(live=False, matching_config=True)
        test_acc.org_name = "Test_account"
        test_acc.update()

        start_of_month = datetime.now(tz=timezone.utc).replace(day=1, hour=0, minute=0, second=0)
        # Create an identifier to add to the live acc
        identifier_value = IdentifierFactory.make_jisc("University of Nowhere").value
        # Add live repo account at the start of the month
        live_acc = AccountFactory.repo_account(live=True, save=False)
        live_acc.live_date = start_of_month.strftime("%Y-%m-%dT%H:%M:%SZ")
        live_acc.org_name = "Live_account"
        live_acc.repository_data.jisc_id = identifier_value
        live_acc.insert()
        AccountFactory.add_config(live_acc)

        live_during_month_acc = AccountFactory.repo_account(live=False, save=False)
        # Set name beginning with "a..." so comes first in report - needed so the assertions below are in the correct order.
        live_during_month_acc.org_name = "Account_made_live_during_month"
        live_during_month_acc.insert()
        AccountFactory.add_config(live_during_month_acc)

        # Create custom zips and add config to the accounts so they match correctly
        zip_name_format = "zip_{}.zip"
        for num in range(10):
            make_custom_zip(pub_one.uuid, zip_name_format.format(num + 1))

        processftp()
        assert UnroutedNotification.count() == 10

        check_unrouted()
        assert RoutedNotification.count() == 10

        year = start_of_month.year
        month = start_of_month.month
        curr_month_start = start_of_month.date()
        jan_date = date(year, 1, 1)
        dec_date = date(year, 12, 1)

        # Sleep so there is enough time between the notifications being sent and the new live date
        time.sleep(1)
        later_live_date = datetime.now(tz=timezone.utc)
        live_during_month_acc.live_date = later_live_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        live_during_month_acc.update()

        # Do the same with more zips (from 2nd publisher) to fill data
        for num in range(10):
            make_custom_zip(pub_two.uuid, zip_name_format.format(num + 11))

        processftp()
        assert UnroutedNotification.count() == 10

        check_unrouted()
        assert RoutedNotification.count() == 20

        # Create monthly data
        MonthlyInstitutionStats.create_monthly_stats_records(curr_month_start, curr_month_start + relativedelta(day=31))

        # Run reports - Code is similar to what is in service/scheduler.py.
        institution_report_live_file = current_app.config.get("REPORTSDIR") + "/institutionLIVE.csv"
        reports.generate_institutions_report(jan_date, dec_date, institution_report_live_file, live_file=True)

        institution_report_test_file = current_app.config.get("REPORTSDIR") + "/institutionTEST.csv"
        reports.generate_institutions_report(jan_date, dec_date, institution_report_test_file, live_file=False)

        # Get the current month's column names.
        month_string = month_num_to_string(month)
        month_content = f"{month_string} content"
        month_total = f"{month_string} Total"
        with open(institution_report_live_file, 'r') as live_csv:
            reader = csv.DictReader(live_csv)
            user_made_live_during_month_row = next(reader)
            assert user_made_live_during_month_row.get("HEI") == live_during_month_acc.org_name
            assert user_made_live_during_month_row.get("Jisc ID") == ''
            assert user_made_live_during_month_row.get("Live Date") == later_live_date.strftime("%Y-%m-%d")
            assert user_made_live_during_month_row.get("Repository") == live_during_month_acc.repository_data.repository_name
            assert user_made_live_during_month_row.get(month_content) == "10"
            assert user_made_live_during_month_row.get(month_total) == "10"

            live_user_row = next(reader)

            assert live_user_row.get("HEI") == live_acc.org_name
            assert live_user_row.get("Jisc ID") == identifier_value
            assert live_user_row.get("Live Date") == start_of_month.strftime("%Y-%m-%d")
            assert live_user_row.get("Repository") == live_acc.repository_data.repository_name
            assert live_user_row.get(month_content) == "20"
            assert live_user_row.get(month_total) == "20"

            total_row = next(reader)
            assert total_row.get(month_content) == "30"
            assert total_row.get(month_total) == "30"

            unique_row = next(reader)
            assert unique_row.get(month_content) == "20"
            assert unique_row.get(month_content) == "20"

        with open(institution_report_test_file, 'r') as test_csv:
            reader = csv.DictReader(test_csv)
            user_made_live_during_month_row = next(reader)
            assert user_made_live_during_month_row.get("HEI") == live_during_month_acc.org_name
            assert user_made_live_during_month_row.get("Jisc ID") == ""
            assert user_made_live_during_month_row.get("Live Date") == later_live_date.strftime("%Y-%m-%d")
            assert user_made_live_during_month_row.get("Repository") == live_during_month_acc.repository_data.repository_name
            assert user_made_live_during_month_row.get(month_content) == "10"
            assert user_made_live_during_month_row.get(month_total) == "10"

            test_user_row = next(reader)
            assert test_user_row.get("HEI") == test_acc.org_name
            assert test_user_row.get("Jisc ID") == ""
            assert test_user_row.get("Live Date") == ""
            assert test_user_row.get("Repository") == test_acc.repository_data.repository_name
            assert test_user_row.get(month_content) == "20"
            assert test_user_row.get(month_total) == "20"

            total_row = next(reader)
            assert total_row.get(month_content) == "30"
            assert total_row.get(month_total) == "30"

            unique_row = next(reader)
            assert unique_row.get(month_content) == "20"
            assert unique_row.get(month_content) == "20"

        ## Create Publisher DOI reports
        reports_generated = reports.generate_all_publisher_doi_to_repos_reports(
            curr_month_start + relativedelta(day=1),
            curr_month_start + relativedelta(day=31),
            current_app.config.get("REPORTSDIR"))

        assert len(reports_generated) == 2
        for emails, csv_path, org_name in reports_generated:
            with open(csv_path, 'r') as csv_file:
                csv_reader = csv.reader(csv_file)
                all_rows = list(csv_reader)
                last_data_row = all_rows[-4]
                assert len(last_data_row) == 4  # Should be 4 columns
                three_totals_rows = all_rows[-3:]
                assert len(three_totals_rows) == 3
                assert three_totals_rows[0][0] == "Total articles:"
                assert three_totals_rows[0][1] == "10"  # 10 articles
                assert three_totals_rows[1][0] == "Total institutions:"
                assert three_totals_rows[1][1] == "2"  # 2 Live institutions
                assert three_totals_rows[2][0] == "Total matches:"
                assert three_totals_rows[2][1] == "20"
                if pub_one.uuid in csv_path:
                    # For pub_one we are expecting 1 row per DOI for 10 routed articles
                    assert len(all_rows) == 14  # Header row + 10 data rows + 3 Totals row
                    # Orgs should be concatenated in alphabetic order
                    assert last_data_row[3] == 'Account_made_live_during_month; Live_account'
                elif pub_two.uuid in csv_path:
                    # For pub_two we are expecting 20 rows ('cos 2 Live repo accounts) per DOI for 10 routed articles
                    assert len(all_rows) == 24  # Header row + 20 data rows + 3 Totals row
                    for ix, val in enumerate(last_data_row):
                        if ix < 3:
                            assert val == ""
                        else:
                            assert val == "Live_account"

    @app_decorator
    def test_04_publisher_report_integration(self):
        """
        Tests All publishers monthly statistics report - showing number of articles submitted, number matched,
        for each publisher for each month.

        Test a full run through of ftp requests being made, processed and routed, followed by a publisher report
        detailing which publishers made these ftp requests and how many were routed successfully.
        Two publishers are involved, pub_one and pub_two. They are expected to have 5 and 4 matches
        respectively, and 10 and 9 successful submissions respectively. Giving us totals of 9 matches and 19 successful
        submissions.
        Test runs as follows:
         - Create two separate publisher accounts for the ftp submissions
         - Create 2 live HEI accounts for routing
         - Create a series of submissions, process and route them
         - Create Publisher monthly statistics csv report
         - Check report values are as expected
        """
        # create the two publisher accounts for testing, name them and ensure their api_keys differ
        pub_one = AccountFactory.publisher_account()
        pub_one.org_name = "TestPublisher1"
        pub_one.update()

        pub_two = AccountFactory.publisher_account()
        pub_two.org_name = "TestPublisher2"
        pub_two.data["api_key"] = "other_pub_key"
        pub_two.publisher_data.report_format = "B"
        pub_two.update()

        start_of_month = datetime.now(tz=timezone.utc).replace(day=1, hour=0, minute=0, second=0)
        # Add live repo account (for routing) at the start of the month
        live_acc = AccountFactory.repo_account(live=True, org_name="Repo University One", matching_config=True)
        live_acc.live_date = start_of_month.strftime("%Y-%m-%dT%H:%M:%SZ")
        live_acc.jisc_id = IdentifierFactory.make_jisc("Repo University One").value
        live_acc.update()

        live_acc2 = AccountFactory.repo_account(live=True, org_name="Repo College Two", matching_config=True)
        live_acc2.live_date = start_of_month.strftime("%Y-%m-%dT%H:%M:%SZ")
        live_acc2.jisc_id = IdentifierFactory.make_jisc("Repo College Two").value
        live_acc.update()

        # create a set of 5 zip files associated with pub_one for ftp submission, then process and route them
        zip_name_format = "zip_{}{}.zip"
        for num in range(5):
            make_custom_zip(pub_one.uuid, zip_name_format.format(pub_one.org_name, num + 1))
        processftp()
        assert UnroutedNotification.count() == 5
        check_unrouted()
        assert RoutedNotification.count() == 5
        assert UnroutedNotification.count() == 0
        # create a set of 4 zip files associated with pub_two for ftp submission, then process and route them
        for num in range(4):
            make_custom_zip(pub_two.uuid, zip_name_format.format(pub_two.org_name, num + 1))
        processftp()
        assert UnroutedNotification.count() == 4
        check_unrouted()
        assert RoutedNotification.count() == 9
        assert UnroutedNotification.count() == 0
        
        # create a set of 5 zip files associated with pub_one and 5 zip files associated with pub_two
        # process these, but do not route them.
        for num in range(5):
            make_custom_zip(pub_one.uuid, zip_name_format.format(pub_one.org_name, num + 1))
        for num in range(5):
            make_custom_zip(pub_two.uuid, zip_name_format.format(pub_two.org_name, num + 1))
        processftp()
        assert UnroutedNotification.count() == 10
        assert RoutedNotification.count() == 9

        # run the report twice, as it ought to be the same regardless
        year = start_of_month.year
        month = start_of_month.month
        curr_month_start = start_of_month.date()
        jan_date = date(year, 1, 1)
        dec_date = date(year, 12, 1)

        # Create monthly data
        MonthlyPublisherStats.create_monthly_stats_records(curr_month_start, curr_month_start + relativedelta(day=31))

        ## Generate Monthly Statistics Report ##
        report_file_path = current_app.config.get("REPORTSDIR") + "/testpublisherLIVE.csv"
        reports.generate_publisher_report(jan_date, dec_date, report_file_path)

        ## Check report created ##
        # get current month's header names, as well as a month's header name which is not this month
        month_name = month_num_to_string(month)
        empty_month_name = month_num_to_string(month + 1)
        if empty_month_name is None:
            empty_month_name = month_num_to_string(month - 1)
        month_received = month_name + " received"
        month_matched = month_name + " matched"
        empty_month_received = empty_month_name + " received"
        empty_month_matched = empty_month_name + " matched"

        ## Open Monthly Publisher Statistics report file & check contents
        with open(report_file_path, 'r') as report_csv:
            csvreader = csv.DictReader(report_csv)
            pub_one_row = next(csvreader, None)
            assert pub_one_row.get("Publisher") == pub_one.org_name
            assert pub_one_row.get(month_received) == "10"
            assert pub_one_row.get(month_matched) == "5"
            assert pub_one_row.get(empty_month_matched) == "0"
            assert pub_one_row.get(empty_month_received) == "0"

            pub_two_row = next(csvreader, None)
            assert pub_two_row.get("Publisher") == pub_two.org_name
            assert pub_two_row.get(month_received) == "9"
            assert pub_two_row.get(month_matched) == "4"
            assert pub_two_row.get(empty_month_received) == "0"

            total_row = next(csvreader, None)
            assert total_row.get("Publisher") == "Total"
            assert total_row.get(month_received) == "19"
            assert total_row.get(month_matched) == "9"
            assert total_row.get(empty_month_matched) == "0"

            # there ought to be no row past this point, so expect the default to be returned by next iterator
            empty_row = next(csvreader, None)
            assert empty_row is None
