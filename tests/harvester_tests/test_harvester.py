"""
Created on 11 Nov 2015

@author: Jisc

This python module contains the unittest created to ensure the correct behaviour of Harvester.
"""
import json
import re
from datetime import datetime
from requests_mock import Mocker
from functools import wraps

# from tests.jper_tests.fixtures.testcase import QueryEngineTest
from router.harvester.app import app_decorator
from router.harvester.harvester_main import StandardGracefulKiller, Harvester
from router.shared.models.harvester import HarvHistoryModel, delete_harvester_indexes, create_harvester_index, HarvestError
from tests.harvester_tests.fixtures.test_data import epmc_api_search_2_results_json, crossref_api_search_2_results_json, epmc_api_search_2_results_nomatch_json
from tests.harvester_tests.fixtures.harvester_utils import HarvesterTestUtils
from tests.fixtures.testcase import JPERMySQLTestCase
from router.harvester.engine.GetEngine import current_app

EPMC_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search/resulttype=core&format=json&query=%20CREATION_DATE%3A%5B{start_date}%20TO%20{end_date}%5D%20&%20OPEN_ACCESS:y%20&%20HAS_PDF:y"
EPMC_URL_MOCK = re.compile(r"^https://www.ebi.ac.uk/europepmc/webservices/rest/search/resulttype")
CROSSREF_URL_MOCK = re.compile(r"^https://api.crossref.org/types/")


"""
Create test versions of index names
"""


def mocker_decorator(real_http=False, mock_tuple_list=None):
    """
    Makes a decorator with the mocker and the app context in scope.

    The mocker is a requests mocker - it will redirect any requests to the API to the flask test client
        instead of doing a real request.

    :param real_http: Boolean - True: allow (pass through) requests that are not mocked; False: Don't action non-mocked
    :param mock_tuple_list: List of tuples: [(url_pattern, return_text), (...), ...]

    :return: Decorator that has the mocker and app context in scope
    """

    def decorator(function):
        @wraps(function)
        @app_decorator
        @Mocker(real_http=real_http)
        def func_wrapper(self, mock_instance):
            if mock_tuple_list:
                for mock_tuple in mock_tuple_list:
                    # ...get(URL pattern, Text to return)
                    mock_instance.get(mock_tuple[0], text=mock_tuple[1])
            function(self)

        return func_wrapper

    return decorator


class HarvesterClientTest(JPERMySQLTestCase):

    @classmethod
    @app_decorator
    def setUpClass(cls):
        # List the tables (by table name) needed for testing
        cls.tables_for_testing = ['metrics', 'harvested_unrouted', 'h_webservice', 'h_errors', 'h_history']

        super(HarvesterClientTest, cls).setUpClass()
        cls.logger = current_app.logger
        cls.config = current_app.config
        cls.test_client = current_app.test_client()
        cls.es_conn = HarvesterTestUtils.es_conn()

    def setUp(self):
        super().setUp()
        # HarvesterTestUtils.create_default_ws_recs()

    @app_decorator
    def tearDown(self):
        # Remove the indexes created for harvesters
        ws_list, ix_list = delete_harvester_indexes(self.es_conn)
        # print("Webservice summary data: ", ws_list)
        # print("Indexes deleted: ", ix_list)
        super().tearDown()

    @classmethod
    @app_decorator
    def clean_and_create(cls):
        """Function to remove existing data from the DB and initialise it with
        indices and mapping for the Harvester structure
        """
        delete_harvester_indexes(cls.es_conn)

    @classmethod
    def create_webservice_rec(cls, engine, name_prefix, end_date_offset=2, **kwargs):
        webservice_dict = HarvesterTestUtils.make_ws_dict(engine.upper(), name_prefix, end_date_offset, **kwargs)
        webservice_id = HarvesterTestUtils.create_ws_record(webservice_dict)
        if webservice_id:
            create_harvester_index(cls.es_conn, engine, webservice_id)

    @staticmethod
    @app_decorator
    def clean_and_create_webservice_rec(engine, name_prefix, end_date_offset=2, **kwargs):
        HarvesterClientTest.clean_and_create()
        HarvesterClientTest.create_webservice_rec(engine, name_prefix, end_date_offset, **kwargs)

    @app_decorator
    def test_wrong_engine_name(self):
        self.logger.info("+++ Test_wrong engine name")

        provider = {'url': EPMC_URL,
                    'query': HarvesterTestUtils.test_url("EPMC"),
                    'name': self.config["EPMC"],
                    'id': 999,
                    'engine': "BAD_ENGINE"
                    }
        today = datetime.today()
        Harvester.killer = StandardGracefulKiller(self.logger)
        Harvester.es_conn = self.es_conn
        Harvester.provider = provider
        Harvester.provider_id = provider["id"]
        Harvester.num_db_errors = 0
        with self.assertRaises(HarvestError) as catch_it:
            Harvester.harvest_provider_and_create_unrouted_notes(today, today)
        the_exception = catch_it.exception
        self.assertTrue("Engine 'BAD_ENGINE' does not exist" in the_exception.message)

    @app_decorator
    def test_no_active_provider(self):
        self.logger.info("+++ Test_no_active_provider")

        self.clean_and_create_webservice_rec(self.config["EPMC"], "TEST_1", active=False)
        self.create_webservice_rec(self.config["PUBMED"], "TEST_2", active=False)

        Harvester.killer = StandardGracefulKiller(self.logger)
        Harvester.es_conn = self.es_conn
        num_providers, _ = Harvester.harvest_all_providers()
        self.assertEqual(0, num_providers)


    def test_no_provider(self):
        self.logger.info("+++ Test_no_provider")

        self.clean_and_create()
        Harvester.killer = StandardGracefulKiller(self.logger)
        Harvester.es_conn = self.es_conn
        num_providers, _ = Harvester.harvest_all_providers()
        self.assertEqual(0, num_providers)


    # Set JSON to be returned by mock call to EPMC
    @mocker_decorator(mock_tuple_list=[(EPMC_URL_MOCK, epmc_api_search_2_results_json)])
    def test_daily(self):
        # Test harvester engine that should be executed today
        self.logger.info("+++ Test daily")

        # EPMC last run yesterday, no wait window - SHOULD RUN TODAY
        self.clean_and_create_webservice_rec(self.config["EPMC"], "TEST_1", end_date_offset=1, wait_window=0)
        # EPMC last run 3 days ago, 2 day wait window - SHOULD RUN TODAY
        self.create_webservice_rec(self.config["EPMC"], "TEST_2", end_date_offset=3, wait_window=2)
        # EPMC last run yesterday, 1 day wait window - SHOULD NOT RUN
        self.create_webservice_rec(self.config["EPMC"], "TEST_3", end_date_offset=1, wait_window=1)

        Harvester.run()

        history_recs = HarvHistoryModel.pull_all(pull_name="all", wrap=False)
        self.assertEqual(2, len(history_recs))
        # Check the 2 history records, they should be for TEST_1 and TEST_2.
        expected_list = [1, 2]
        for rec in history_recs:
            for expected in expected_list:
                self.assertEqual(2, rec["num_received"])
                self.assertEqual(2, rec["num_sent"])
                if rec["ws_id"] == expected:
                    expected_list.remove(expected)
                    break

        self.assertEqual(expected_list, [])

        self.logger.info("+++ Test that webservices aren't executed again if already run today")
        # Run harvester again - None of the harvesters should run - Number of history recs should not change
        Harvester.run()

        history_recs = HarvHistoryModel.pull_all(pull_name="all", wrap=False)
        self.assertEqual(2, len(history_recs))

    # Set JSON to be returned by mock call to EPMC
    @mocker_decorator(mock_tuple_list=[(EPMC_URL_MOCK, epmc_api_search_2_results_nomatch_json)])
    def test_daily_nomatch(self):
        # Test harvester engine that should be executed today
        self.logger.info("+++ Test epmc daily no match in retrieved data")

        # EPMC last run yesterday, no wait window - SHOULD RUN TODAY
        self.clean_and_create_webservice_rec(self.config["EPMC"], "TEST_1", end_date_offset=1, wait_window=0)

        Harvester.run()

        history_recs = HarvHistoryModel.pull_all(pull_name="all", wrap=False)
        self.assertEqual(1, len(history_recs))

        # Check the history record, confirm 2 "files" received, none sent
        hist_rec = history_recs[0]
        self.assertEqual(2, hist_rec["num_received"])
        self.assertEqual(0, hist_rec["num_sent"])


    # Set JSON to be returned by mock call to EPMC
    @mocker_decorator(mock_tuple_list=[(EPMC_URL_MOCK, epmc_api_search_2_results_json)])
    def test_several_provider_wrong_url(self):
        self.logger.info("+++ Test_several provider one with wrong url")

        bad_url = "BAD_URL"
        self.clean_and_create_webservice_rec(self.config["EPMC"], "TEST_OK")
        self.create_webservice_rec(self.config["EPMC"], "TEST_BAD", url=bad_url)

        Harvester.run()
        history_recs = HarvHistoryModel.pull_all(pull_name="all", wrap=False)
        self.assertEqual(2, len(history_recs))
        # Check the 2 history records, one with the bad URL should have an error message, the other not.
        for rec in history_recs:
            if rec["url"] == bad_url:
                assert rec["num_errors"] > 0
                assert rec["num_received"] == 0
            else:
                assert rec["num_errors"] == 0
                assert rec["num_received"] == 2


    # Set JSON to be returned by mock call to EPMC
    @mocker_decorator(mock_tuple_list=[(EPMC_URL_MOCK, epmc_api_search_2_results_json)])
    def test_several_provider_wrong_query(self):
        self.logger.info("+++ Test_several provider wrong query")

        bad_query = json.dumps({'query': 'BAD_QUERY'})
        self.clean_and_create_webservice_rec(self.config["EPMC"], "TEST_BAD", query=bad_query)
        self.create_webservice_rec(self.config["EPMC"], "TEST_OK")
        Harvester.run()
        history_recs = HarvHistoryModel.pull_all(pull_name="all", wrap=False)
        self.assertEqual(2, len(history_recs))
        # Check the 2 history records, one with the bad Query should have an error message, the other not.
        for rec in history_recs:
            assert rec["num_received"] == 2
            if rec["ws_id"] == 1:
                assert rec["num_errors"] == 1
            else:
                assert rec["num_errors"] == 0


    # Set JSON to be returned by mock call to EPMC
    @mocker_decorator(mock_tuple_list=[(EPMC_URL_MOCK, epmc_api_search_2_results_json)])
    def test_weekly_with_data(self):
        # Test a weekly harvester engine that should be executed today
        self.logger.info("+++ Test_weekly with data")

        # EPMC last run 8 days ago, no wait window - SHOULD RUN TODAY
        self.clean_and_create_webservice_rec(self.config["EPMC"], "TEST_1", frequency="weekly", end_date_offset=8, wait_window=0)
        # EPMC last run 11 days ago, 3 day wait window - SHOULD RUN TODAY
        self.create_webservice_rec(self.config["EPMC"], "TEST_2", frequency="weekly", end_date_offset=11, wait_window=3)
        # EPMC last run 5 days ago, 1 day wait window - SHOULD NOT RUN
        self.create_webservice_rec(self.config["EPMC"], "TEST_3", frequency="weekly", end_date_offset=5, wait_window=1)

        Harvester.run()

        history_recs = HarvHistoryModel.pull_all(pull_name="all", wrap=False)
        self.assertEqual(2, len(history_recs))
        # Check the 2 history records, they should be for TEST_1 and TEST_2.
        expected_list = [1, 2]
        for rec in history_recs:
            for expected in expected_list:
                if rec["ws_id"] == expected:
                    expected_list.remove(expected)
                    break

        self.assertEqual(expected_list, [])

        self.logger.info("+++ Test that webservices aren't executed again if already run today")
        # Run harvester again - None of the harvesters should run - Number of history recs should not change
        Harvester.run()

        history_recs = HarvHistoryModel.pull_all(pull_name="all", wrap=False)
        self.assertEqual(2, len(history_recs))


    def test_wrong_frequency_name(self):
        self.logger.info("+++ Test_wrong frequency name")

        self.clean_and_create_webservice_rec(self.config["EPMC"], "TEST_BAD", frequency="BAD_FREQ")
        Harvester.killer = StandardGracefulKiller(self.logger)
        Harvester.es_conn = self.es_conn
        result, _ = Harvester.harvest_all_providers()
        self.assertEqual(0, result)


    @mocker_decorator(mock_tuple_list=[(CROSSREF_URL_MOCK, crossref_api_search_2_results_json)])
    def test_daily_crossref_data(self):
        self.logger.info("+++ test_daily_crossref_data")

        # Crossref last run yesterday, no wait window - SHOULD RUN TODAY
        self.clean_and_create_webservice_rec(self.config["CROSSREF"], "TEST_1", end_date_offset=10, wait_window=9)

        Harvester.run()
        history_recs = HarvHistoryModel.pull_all(pull_name="all", wrap=False)
        self.assertEqual(1, len(history_recs))



