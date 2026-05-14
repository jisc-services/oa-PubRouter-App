import json
from os import path
import codecs
from copy import deepcopy
from dateutil.relativedelta import relativedelta
from testfixtures import compare
from unittest import TestCase
from requests_mock import Mocker

from octopus.lib.exceptions import RESTError
from router.harvester.app import app_decorator
from router.harvester.engine.QueryEngineCrossref import QueryEngineCrossref, _CrossrefCursor
from tests.harvester_tests.test_engine.query_engine_test_base import QueryEngineTest


def json_file_to_dict(file_location):
    json_file = codecs.open(file_location, 'r', 'utf-8')
    returned_dict = json.loads(json_file.read())
    json_file.close()
    return returned_dict


DEFAULT_URL = (
    'https://api.crossref.org/works?filter=from-update-date:{start_date},until-update-date:{end_date},'
    'from-pub-date:{pub_year},has-affiliation:true,has-orcid:true&rows=1000'
)


URL_TEST_URL = (
    'https://api.crossref.org/works?'
    'filter=from-update-date:{start_date},until-update-date:{end_date},from-pub-date:{pub_year}&rows=10'
)

FAKE_PAGE_10_ITEMS_30_TOTAL = {
    "message": {
        "items": [{"article": "dummy-0"},
                  {"article": "dummy-1"},
                  {"article": "dummy-2"},
                  {"article": "dummy-3"},
                  {"article": "dummy-4"},
                  {"article": "dummy-5"},
                  {"article": "dummy-6"},
                  {"article": "dummy-7"},
                  {"article": "dummy-8"},
                  {"article": "dummy-9"},
                  ],
        "total-results": 30,
        "next-cursor": "fakecursor"
    }
}

HARVESTER_ID = 'test_crossref'

__test_file_path = path.join(path.dirname(path.abspath(__file__)), "..", "resources")

crossref_dict = json_file_to_dict(path.join(__test_file_path, 'crossrefjson.json'))
crossref_response = json_file_to_dict(path.join(__test_file_path, 'crossrefresponse.json'))

incoming_notification = {
    "category": "JA",
    "metadata": {
        "funding": [{
            "grant_numbers": ["NE/L005212/1", "NE/L005212/2"],
            "identifier": [{
                "type": "FundRef",
                "id": "10.13039/501100000270"
            }],
            "name": "Natural Environment Research Council"
        }
        ],
        "author": [{
            "affiliations": [{"raw": "British Antarctic Survey; Natural Environment Research Council; Cambridge UK"}],
            "identifier": [{
                "type": "orcid",
                "id": "0000-0002-3762-8219"
            }],
            "name": {
                "fullname": "Arthern, Robert J.",
                "surname": "Arthern",
                "firstname": "Robert J."
            }
        }, {
            "affiliations": [{"raw": "British Antarctic Survey; Natural Environment Research Council; Cambridge UK"}],
            "identifier": [{
                "type": "orcid",
                "id": "0000-0002-8131-4946"
            }],
            "name": {
                "fullname": "Williams, C. Rosie",
                "surname": "Williams",
                "firstname": "C. Rosie"
            }
        }
        ],
        "license_ref": [{
                "url": "http://creativecommons.org/licenses/by/4.0/",
                "start": "2017-03-11"
            }],
        "journal": {
            "publisher": ["Wiley-Blackwell"],
            "identifier": [{
                "type": "pissn",
                "id": "0094-8276"
            }
            ],
            "title": "Geophysical Research Letters",
            "abbrev_title": "Geophys. Res. Lett."
        },
        "publication_date": {
            "publication_format": "electronic",
            "year": "2017",
            "date": "2017-03-11",
            "month": "03",
            "day": "11"
        },
        "publication_status": "Published",
        "accepted_date": "2017-01-22",
        "history_date": [{
            "date_type": "epub",
            "date": "2017-03-11"
        },{
            "date_type": "accepted",
            "date": "2017-01-22"
        },{
            "date_type": "published",
            "date": "2017-03-11"
        }
        ],
        "contributor": [],
        "article": {
            "identifier": [{
                "type": "doi",
                "id": "10.1002/2017gl072514"
            }],
            "abstract": "<jats:title>Abstract</jats:title><jats:p> <jats:bold>Objectives:</jats:bold> The Addenbrooke’s Cognitive Examination (ACE) is a common cognitive screening test for dementia. Here, we examined the relationship between the most recent version (ACE-III) and its predecessor (ACE-R), determined ACE-III cutoff scores for the detection of dementia, and explored its relationship with functional ability. <jats:bold>Methods:</jats:bold> Study 1 included 199 dementia patients and 52 healthy controls who completed the ACE-III and ACE-R. ACE-III total and domain scores were regressed on their corresponding ACE-R values to obtain conversion formulae. Study 2 included 331 mixed dementia patients and 87 controls to establish the optimal ACE-III cutoff scores for the detection of dementia using receiver operator curve analysis. Study 3 included 194 dementia patients and their carers to investigate the relationship between ACE-III total score and functional ability. <jats:bold>Results:</jats:bold> Study 1: ACE-III and ACE-R scores differed by ≤1 point overall, the magnitude varying according to dementia type. Study 2: a new lower bound cutoff ACE-III score of 84/100 to detect dementia was identified (compared with 82 for the ACE-R). The upper bound cutoff score of 88/100 was retained. Study 3: ACE-III scores were significantly related to functional ability on the Clinical Dementia Rating Scale across all dementia syndromes, except for semantic dementia. <jats:bold>Conclusions:</jats:bold> This study represents one of the largest and most clinically diverse investigations of the ACE-III. Our results demonstrate that the ACE-III is an acceptable alternative to the ACE-R. In addition, ACE-III performance has broader clinical implications in that it relates to carer reports of functional impairment in most common dementias. (<jats:italic>JINS</jats:italic>, 2018, <jats:italic>24</jats:italic>, 854–863)</jats:p>",
            "version": "VOR",
            "type": "journal-article",
            "subject": ["Earth and Planetary Sciences(all)", "Geophysics"],
            "title": "The sensitivity of West Antarctica to the submarine melting feedback"
        }
    },
    "provider": {
        "harv_id": 88,
        "route": "harv",
        "agent": "Crossref",
        "rank": 3
    }
}

correct_page_info = {
    "start_page": "123",
    "end_page": "145",
    "num_pages": 5,
    "page_range": "123-126,145"
}

class TestQueryEngineCrossref(QueryEngineTest):

    def setUp(self):
        # ensure state is maintained between test cases
        super().setUp()
        self.incoming_notification = deepcopy(incoming_notification)
        self.crossref_dict = deepcopy(crossref_dict)

    def construct_default_engine(self, date=None, url=DEFAULT_URL):
        start_date = date
        end_date = date
        engine = QueryEngineCrossref(self.es_db, url, HARVESTER_ID, start_date, end_date, "Crossref")
        return engine

    def date_modify(self, months, crossref=True):
        # returns a time object which is respective of today's date for testing
        # depending on crossref's value, returns date in crossref json format or incomingnotification json format
        modified_date = self.today + relativedelta(months=months)
        if crossref:
            return {
                "date-parts": [[modified_date.year, modified_date.month, modified_date.day]],
                "date-time": "",
                "timestamp": 0
            }
        return modified_date.strftime("%Y-%m-%d")

    @staticmethod
    def make_license_dict(version, url, start=""):
        # based on a list of parameters, construct an IncomingNotification license object
        return {
            "url": url,
            "start": start
        }

    @staticmethod
    def construct_license_crossref(version, url, start=None):
        # based on a list of parameters, construct a Crossref license object
        if start:
            license = {
                "URL": url,
                "start": start,
                "delay-in-days": "",
                "content-version": version
            }
        else:
            license = {
                "URL": url,
                "delay-in-days": "",
                "content-version": version
            }
        return license

    @staticmethod
    def set_cursor_url_and_fake_json_results(initial_url, num):
        """
        Create url with a particular cursor and a page of fake json results
        :param initial_url: String - the initial URL (without any cursor attached)
        :param num: number to append to current cursor
        :return: Tuple: url-with-cursor-string, fake-page-of-results-dict
        """
        fake_page = deepcopy(FAKE_PAGE_10_ITEMS_30_TOTAL)
        fake_page["message"]["next-cursor"] = f"fakecursor_{num + 1}"
        return f"{initial_url}&cursor=fakecursor_{num}", fake_page

    def create_engine_and_add_mocked_urls(self, mocker, date=None, num_mock_urls=2, num_rows=None):
        """
        Create an engine and then mock the URLs that engine will use.

        This stops the test requiring actually requesting the crossref API.

        :param mocker: requests mock object created from a Mocker() decorator
        :param date: Date object if wanted
        :param num_mock_urls: 0 - no cursor urls, >0 - Number of cursor URLs
        :param num_rows: Number of rows required

        :return: Tuple (QueryEngineCrossref instance created by construct_default_engine, initial_url)
        """
        url = DEFAULT_URL
        engine = self.construct_default_engine(date, url=url)
        initial_url = engine.format_url(url, date, date, num_rows)
        first_request_url = f'{initial_url}{"&cursor=*" if num_mock_urls else ""}'
        mocker.get(first_request_url, json=crossref_response)
        for x in range(0, num_mock_urls):
            cursor_url, fake_page = self.set_cursor_url_and_fake_json_results(initial_url, x)
            mocker.get(cursor_url, json=fake_page)
        return engine, initial_url

    def edit_notification(self, licenses, article_version=None, embargo_end=None):
        """
        given a set of licenses, an article version and embargo date, make relevant changes to the
        IncomingNotification structure
        :param licenses: set of licenses we're adding to IncomingNotification
        :param article_version: the article version we're setting (can be None)
        :param embargo_end: the embargo_end date we're setting (can be None)
        """
        # set the licenses
        self.incoming_notification["metadata"]["license_ref"] = licenses
        # if an article version exists, set it
        if article_version:
            self.incoming_notification["metadata"]["article"]["version"] = article_version
        # attempt to delete article version
        else:
            try:
                # if article version exists, delete it. Otherwise pass
                del self.incoming_notification["metadata"]["article"]["version"]
            except KeyError:
                pass
        # if a value for embargo is passed, set it
        if embargo_end:
            self.incoming_notification["metadata"]["embargo"] = {"end": embargo_end}
        # attempt to delete embargo information
        else:
            try:
                # delete embargo information, if there is embargo information there. Otherwise pass
                del self.incoming_notification["metadata"]["embargo"]
            except KeyError:
                pass

    @app_decorator
    def run_test(self, crossref_licenses=None, notification_licenses=None, article_version=None, embargo_end=None):
        """
        Method takes a set of crossref_licenses, notification_licenses, a valid article version and an embargo date,
        and uses this data to set up a test in which we check to see whether the output of
        convert_to_notification(crossref_license) is as expected.
        """
        if crossref_licenses is None:
            return

        # build our crossref engine
        engine = self.construct_default_engine(self.date_today)
        # set our crossref notification for processing
        self.crossref_dict["license"] = crossref_licenses
        # set our IncomingNotification for comparison
        self.edit_notification(notification_licenses, article_version, embargo_end)
        # process our crossref notification
        notification_dict = engine.convert_to_notification(self.crossref_dict, 88)
        # compare the processed notification with the expected value
        compare(notification_dict, self.incoming_notification)

    @app_decorator
    @Mocker()
    def test_default_value(self, m):
        engine, null = self.create_engine_and_add_mocked_urls(m)
        engine.create_harvester_ix()
        number_of_results = engine.execute()
        engine.delete_harvester_ix()
        assert number_of_results == 30

    @app_decorator
    @Mocker()
    def test_simple_import(self, m):
        engine, null = self.create_engine_and_add_mocked_urls(m, self.date_today)
        engine.create_harvester_ix()
        number_of_results = engine.execute()
        engine.delete_harvester_ix()
        assert number_of_results == 30

    @app_decorator
    def test_page_info(self):
        engine = self.construct_default_engine()
        page_info = engine.construct_page_info("123-126,145")
        compare(correct_page_info, page_info)

    @app_decorator
    def test_garbage_parts(self):
        engine = self.construct_default_engine()
        garbage = engine.date_dict_from_ymd_list([[None]])
        self.assertTrue(garbage, {})

    @app_decorator
    @Mocker()
    def test_valid_invalid_urls(self, mocker):
        engine, null = self.create_engine_and_add_mocked_urls(mocker, num_mock_urls=0, num_rows=2)
        self.assertTrue(engine.is_valid(DEFAULT_URL))

        bad_url = "https://api.crossref.org/works?filter=bad-value:true"
        mocker.get(bad_url, text="...bad request...", reason="Bad Request", status_code=400)
        self.assertFalse(engine.is_valid(bad_url))

    @app_decorator
    @Mocker()
    def test_cursor_retry_success(self, mocker):
        save_sleep = _CrossrefCursor.SLEEP
        _CrossrefCursor.SLEEP = 0     # Seconds
        engine, init_url = self.create_engine_and_add_mocked_urls(mocker, num_mock_urls=1)
        cursor_url, fake_page = self.set_cursor_url_and_fake_json_results(init_url, 1)
        # Set mocker to return two error responses, followed by successful response
        mocker.get(cursor_url, [{"text": "...server error...", "reason": "Server Error", "status_code": 500},
                                {"text": "...server error...", "reason": "Server Error", "status_code": 500},
                                {"json": fake_page, "status_code": 200}])
        engine.create_harvester_ix()
        number_of_results = engine.execute()
        engine.delete_harvester_ix()
        _CrossrefCursor.SLEEP = save_sleep
        assert number_of_results == 30

    @app_decorator
    @Mocker()
    def test_cursor_retry_fail(self, mocker):
        save_sleep = _CrossrefCursor.SLEEP
        _CrossrefCursor.SLEEP = 0
        save_tries = _CrossrefCursor.TRIES
        _CrossrefCursor.TRIES = 3
        engine, init_url = self.create_engine_and_add_mocked_urls(mocker, num_mock_urls=1)
        cursor_url, fake_page = self.set_cursor_url_and_fake_json_results(init_url, 1)
        # Set mocker to return three error responses, followed by successful response
        mocker.get(cursor_url, [{"text": "...server error...", "reason": "Server Error-1", "status_code": 500},
                                {"text": "...server error...", "reason": "Server Error-2", "status_code": 500},
                                {"text": "...server error...", "reason": "Server Error-4", "status_code": 500},
                                {"json": fake_page, "status_code": 200}])
        engine.create_harvester_ix()
        with self.assertRaises(RESTError) as catch_it:
            number_of_results = engine.execute()
        engine.delete_harvester_ix()
        _CrossrefCursor.SLEEP = save_sleep
        _CrossrefCursor.TRIES = save_tries

        exception_err = str(catch_it.exception)
        assert "500 Server Error" in exception_err
        assert cursor_url in exception_err


    @app_decorator
    def test_full_json(self):
        engine = self.construct_default_engine(self.date_today)
        notification_dict = engine.convert_to_notification(self.crossref_dict, 88)
        compare(sorted(notification_dict.items()), sorted(self.incoming_notification.items()))

    # the following tests are modelled on test cases described in the document
    # https://jisc365.sharepoint.com/sites/dcrd/openacc/_layouts/15/DocIdRedir.aspx?ID=5A7VYUX4WZA7-1270856285-32729&e=JVnOty
    def test_article_one_open_license(self):
        """
        A test of this nature involves the following steps:
         - set up a list of crossref_licenses, to be processed
         - set up a list of notification_licenses, to be used in comparison
         - run the test, with expected parameters
         Ensure to use self.date_modify() in these tests, so that dates are respective to current time. Use an
         additional argument to this function of False, when setting notification_licenses time.
        """
        open_license = "http://creativecommons.org/licenses/by/4.0/"
        closed_license = "http://notanopenlicense.org"
        crossref_licenses = [
            self.construct_license_crossref("VoR", open_license)
        ]
        notification_licenses = [
            self.make_license_dict("VoR", open_license)
        ]
        self.run_test(crossref_licenses, notification_licenses, "VOR")

        crossref_licenses = [
            self.construct_license_crossref("VoR", open_license),
            self.construct_license_crossref("VoR", closed_license, self.date_modify(-6, crossref=True))
        ]
        notification_licenses = [
            self.make_license_dict("VoR", open_license),
            self.make_license_dict("VoR", closed_license, self.date_modify(-6, crossref=False))
        ]
        self.run_test(crossref_licenses, notification_licenses, "VOR")
        crossref_licenses = [
            self.construct_license_crossref("VoR", open_license, self.date_modify(-12, crossref=True)),
            self.construct_license_crossref("VoR", closed_license, self.date_modify(-6, crossref=True))
        ]
        notification_licenses = [
            self.make_license_dict("VoR", open_license, self.date_modify(-12, crossref=False)),
            self.make_license_dict("VoR", closed_license, self.date_modify(-6, crossref=False))
        ]
        self.run_test(crossref_licenses, notification_licenses, "VOR")
        crossref_licenses = [
            self.construct_license_crossref("AM", open_license),
            self.construct_license_crossref("VoR", closed_license)
        ]
        notification_licenses = [
            self.make_license_dict("AM", open_license)
        ]
        self.run_test(crossref_licenses, notification_licenses, "AM")

    def test_article_one_open_in_past(self):
        open_license = "http://creativecommons.org/licenses/by/4.0/"
        closed_license = "http://notanopenlicense.org"
        crossref_licenses = [
            self.construct_license_crossref("VoR", closed_license, self.date_modify(-12, crossref=True)),
            self.construct_license_crossref("AM", open_license),
            self.construct_license_crossref("VoR", open_license, self.date_modify(12, crossref=True))
        ]
        notification_licenses = [
            self.make_license_dict("AM", open_license)
        ]
        self.run_test(crossref_licenses, notification_licenses, "AM")
        crossref_licenses = [
            self.construct_license_crossref("VoR", closed_license, self.date_modify(-12, crossref=True)),
            self.construct_license_crossref("VoR", open_license),
            self.construct_license_crossref("AM", open_license, self.date_modify(12, crossref=True))
        ]
        notification_licenses = [
            self.make_license_dict("VoR", closed_license, self.date_modify(-12, crossref=False)),
            self.make_license_dict("VoR", open_license)
        ]
        self.run_test(crossref_licenses, notification_licenses, "VOR")
        crossref_licenses = [
            self.construct_license_crossref("AM", closed_license, self.date_modify(-12, crossref=True)),
            self.construct_license_crossref("AM", open_license, self.date_modify(-12, crossref=True)),
            self.construct_license_crossref("VoR", open_license, self.date_modify(12, crossref=True))
        ]
        notification_licenses = [
            self.make_license_dict("AM", closed_license, self.date_modify(-12, crossref=False)),
            self.make_license_dict("AM", open_license, self.date_modify(-12, crossref=False))
        ]
        self.run_test(crossref_licenses, notification_licenses, "AM")

    def test_multiple_past_open_licenses(self):
        open_license = "http://creativecommons.org/licenses/by/4.0/"
        closed_license = "http://notanopenlicense.org"
        crossref_licenses = [
            self.construct_license_crossref("VoR", closed_license, self.date_modify(-12, crossref=True)),
            self.construct_license_crossref("AM", open_license, self.date_modify(-6, crossref=True)),
            self.construct_license_crossref("VoR", open_license)
        ]
        notification_licenses = [
            self.make_license_dict("VoR", closed_license, self.date_modify(-12, crossref=False)),
            self.make_license_dict("VoR", open_license)
        ]
        self.run_test(crossref_licenses, notification_licenses, "VOR")

        crossref_licenses = [
            self.construct_license_crossref("VoR", closed_license, self.date_modify(-12, crossref=True)),
            self.construct_license_crossref("AM", open_license),
            self.construct_license_crossref("VoR", open_license, self.date_modify(-7, crossref=True))
        ]
        notification_licenses = [
            self.make_license_dict("VoR", closed_license, self.date_modify(-12, crossref=False)),
            self.make_license_dict("VoR", open_license, self.date_modify(-7, crossref=False))
        ]
        self.run_test(crossref_licenses, notification_licenses, "VOR")

        crossref_licenses = [
            self.construct_license_crossref("VoR", closed_license, self.date_modify(-12, crossref=True)),
            self.construct_license_crossref("AM", open_license, self.date_modify(-1, crossref=True)),
            self.construct_license_crossref("VoR", open_license, self.date_modify(-12, crossref=True))
        ]
        notification_licenses = [
            self.make_license_dict("VoR", closed_license, self.date_modify(-12, crossref=False)),
            self.make_license_dict("VoR", open_license, self.date_modify(-12, crossref=False))
        ]
        self.run_test(crossref_licenses, notification_licenses, "VOR")
        crossref_licenses = [
            self.construct_license_crossref("VoR", closed_license, self.date_modify(-12, crossref=True)),
            self.construct_license_crossref("AM", open_license, self.date_modify(-6, crossref=True)),
            self.construct_license_crossref("P", open_license, self.date_modify(-3, crossref=True))
        ]
        notification_licenses = [
            self.make_license_dict("P", open_license, self.date_modify(-3, crossref=False))
        ]
        self.run_test(crossref_licenses, notification_licenses, "P")
        crossref_licenses = [
            self.construct_license_crossref("VoR", closed_license, self.date_modify(-12, crossref=True)),
            self.construct_license_crossref("AM", open_license, self.date_modify(-6, crossref=True)),
            self.construct_license_crossref("VoR", open_license, self.date_modify(-6, crossref=True))
        ]
        notification_licenses = [
            self.make_license_dict("VoR", closed_license, self.date_modify(-12, crossref=False)),
            self.make_license_dict("VoR", open_license, self.date_modify(-6, crossref=False))
        ]
        self.run_test(crossref_licenses, notification_licenses, "VOR")

    def test_multiple_open_in_future(self):
        open_license = "http://creativecommons.org/licenses/by/4.0/"
        closed_license = "http://notanopenlicense.org"
        crossref_licenses = [
            self.construct_license_crossref("VoR", closed_license, self.date_modify(-6, crossref=True)),
            self.construct_license_crossref("AM", open_license, self.date_modify(12, crossref=True))
        ]
        notification_licenses = [
            self.make_license_dict("AM", open_license, self.date_modify(12, crossref=False))
        ]
        self.run_test(crossref_licenses, notification_licenses, "AM", self.date_modify(12, crossref=False))

        crossref_licenses = [
            self.construct_license_crossref("VoR", closed_license, self.date_modify(-12, crossref=True)),
            self.construct_license_crossref("AM", open_license, self.date_modify(3, crossref=True)),
            self.construct_license_crossref("VoR", open_license, self.date_modify(6, crossref=True))
        ]
        notification_licenses = [
            self.make_license_dict("AM", open_license, self.date_modify(3, crossref=False))
        ]
        self.run_test(crossref_licenses, notification_licenses, "AM", self.date_modify(3, crossref=False))
        crossref_licenses = [
            self.construct_license_crossref("VoR", closed_license, self.date_modify(-12, crossref=True)),
            self.construct_license_crossref("AM", open_license, self.date_modify(12, crossref=True)),
            self.construct_license_crossref("VoR", open_license, self.date_modify(6, crossref=True))
        ]
        notification_licenses = [
            self.make_license_dict("VoR", closed_license, self.date_modify(-12, crossref=False)),
            self.make_license_dict("VoR", open_license, self.date_modify(6, crossref=False))
        ]
        self.run_test(crossref_licenses, notification_licenses, "VOR", self.date_modify(6, crossref=False))
        crossref_licenses = [
            self.construct_license_crossref("VoR", closed_license, self.date_modify(-12, crossref=True)),
            self.construct_license_crossref("AM", open_license, self.date_modify(12, crossref=True)),
            self.construct_license_crossref("P", open_license, self.date_modify(12, crossref=True))
        ]
        notification_licenses = [
            self.make_license_dict("P", open_license, self.date_modify(12, crossref=False))
        ]
        self.run_test(crossref_licenses, notification_licenses, "P", self.date_modify(12, crossref=False))

    def test_only_one_closed(self):
        closed_license = "http://notanopenlicense.org"
        crossref_licenses = [
            self.construct_license_crossref("VoR", closed_license, self.date_modify(-12, crossref=True))
        ]
        notification_licenses = [
            self.make_license_dict("VoR", closed_license, self.date_modify(-12, crossref=False))
        ]
        self.run_test(crossref_licenses, notification_licenses, "VOR")
        crossref_licenses = [
            self.construct_license_crossref("P", closed_license)
        ]
        notification_licenses = [
            self.make_license_dict("P", closed_license)
        ]
        self.run_test(crossref_licenses, notification_licenses, "P")

    def test_only_closed_multiple(self):
        closed_license = "http://notanopenlicense.org"
        crossref_licenses = [
            self.construct_license_crossref("VoR", closed_license, self.date_modify(-12, crossref=True)),
            self.construct_license_crossref("AM", closed_license, self.date_modify(6, crossref=True))
        ]
        notification_licenses = [
            self.make_license_dict("AM", closed_license, self.date_modify(6, crossref=False))
        ]
        self.run_test(crossref_licenses, notification_licenses, "AM")

        crossref_licenses = [
            self.construct_license_crossref("VoR", closed_license, self.date_modify(-12, crossref=True)),
            self.construct_license_crossref("AM", closed_license, self.date_modify(-6, crossref=True)),
            self.construct_license_crossref("AM", closed_license, self.date_modify(6, crossref=True))
        ]
        notification_licenses = [
            self.make_license_dict("AM", closed_license, self.date_modify(-6, crossref=False)),
            self.make_license_dict("AM", closed_license, self.date_modify(6, crossref=False))
        ]
        self.run_test(crossref_licenses, notification_licenses, "AM")
        crossref_licenses = [
            self.construct_license_crossref("VoR", closed_license, self.date_modify(-12, crossref=True)),
            self.construct_license_crossref("VoR", closed_license, self.date_modify(6, crossref=True)),
            self.construct_license_crossref("AM", closed_license, self.date_modify(6, crossref=True))
        ]
        notification_licenses = [
            self.make_license_dict("AM", closed_license, self.date_modify(6, crossref=False))
        ]
        self.run_test(crossref_licenses, notification_licenses, "AM")

    def test_no_valid_licenses(self):
        open_license = "http://creativecommons.org/licenses/by/4.0/"
        closed_license = "http://notanopenlicense.org"
        crossref_licenses = [
            self.construct_license_crossref("tdm", closed_license, self.date_modify(-12, crossref=True)),
            self.construct_license_crossref("notinthelist", open_license, self.date_modify(6, crossref=True))
        ]
        notification_licenses = []
        self.run_test(crossref_licenses, notification_licenses, article_version=None)

    @app_decorator
    def test_no_electronic_date(self):
        # check that when there is no online date, we take from printed
        engine = self.construct_default_engine(self.date_today)
        # remove online date
        del self.crossref_dict["published-online"]
        # change our expected return value
        self.incoming_notification["metadata"]["publication_date"] = {
            "publication_format": "print",
            "year": "2017"
        }
        del self.incoming_notification["metadata"]["history_date"][0]
        # process our crossref notification
        notification_dict = engine.convert_to_notification(self.crossref_dict, 88)
        # compare the processed notification with the expected value
        compare(sorted(notification_dict.items()), sorted(self.incoming_notification.items()))

    @app_decorator
    def test_no_electronic_printed_date(self):
        # check that when there is no online or printed date, we take from issued with no publication_format
        engine = self.construct_default_engine(self.date_today)
        # remove online and printed dates
        del self.crossref_dict["published-online"]
        del self.crossref_dict["published-print"]
        # change our expected return value
        self.incoming_notification["metadata"]["publication_date"] = {"year": "2017"}   # no publication_format
        del self.incoming_notification["metadata"]["history_date"][0]
        # process our crossref notification
        notification_dict = engine.convert_to_notification(self.crossref_dict, 88)
        # compare the processed notification with the expected value
        compare(sorted(notification_dict.items()), sorted(self.incoming_notification.items()))

    @app_decorator
    def test_string_only_abstract(self):
        # check that when there are no xml tags in the abstract string that this works identically to if there are
        engine = self.construct_default_engine(self.date_today)
        # set abstract values to be strings only (no xml tags)
        self.crossref_dict["abstract"] = "string only"
        self.incoming_notification["metadata"]["article"]["abstract"] = "string only"
        # process our crossref notification
        notification_dict = engine.convert_to_notification(self.crossref_dict, 88)
        # compare the processed notification with the expected value
        compare(sorted(notification_dict.items()), sorted(self.incoming_notification.items()))


class TestCrossrefNotificationArticleTypes(TestCase):
    """
    Check that the metadata.article.type is set correctly in notification data harvested from the
    following Crossref feeds by checking the values returned by convert_to_notification:
        - book chapters
        - journal articles
        - monographs
        - posted content (pre-prints and other)
        - proceedings articles
        - reports
    """

    @app_decorator
    def setUp(self):
        """
        Create the Crossref Query engine. Don't bother using realistic arguments - we won't be
        executing the engine, just a single method, so we don't need them.
        """
        url = "don't care"
        self.engine = QueryEngineCrossref(None, url, HARVESTER_ID, name_ws='')

    def get_resource_path(self, name):
        return path.join(path.dirname(path.abspath(__file__)), '..', 'resources', name)

    @app_decorator
    def test_book_chapters(self):
        """
        Test that a Notification created from a document harvested from the 'book-chapters'
        Crossref feed has its article.type set to "book-chapter".
        """
        doc = json_file_to_dict(self.get_resource_path('crossref-book-chapter-doc.json'))
        note_dict = self.engine.convert_to_notification(doc)
        assert note_dict['metadata']['article']['type'] == 'book-chapter'

    @app_decorator
    def test_journal_articles(self):
        """
        Test that a Notification created from a document harvested from the
        'journal-articles' Crossref feed has its article.type set to "journal-article".
        """
        doc = json_file_to_dict(self.get_resource_path('crossref-journal-article-doc.json'))
        note_dict = self.engine.convert_to_notification(doc)
        assert note_dict['metadata']['article']['type'] == 'journal-article'
        assert note_dict['metadata']['author'][0]['affiliations'] == [
            {'raw': 'Department of Biochemistry and Genetics, University of Navarra School of Sciences, 31008 Pamplona, Spain'},
            {'raw': 'Department of Biochemistry and Genetics, University of Navarra School of Sciences, Pamplona, Spain',
             'identifier': [{'type': 'ROR', 'id': 'https://ror.org/02rxc7m23'}],
             'dept': 'Department of Biochemistry and Genetics'},
            {'identifier': [{'type': 'ROR', 'id': 'https://ror.org/02rxc7m23'}]}
        ]

    @app_decorator
    def test_report(self):
        """
        Test that a Notification created from a document harvested from the
        'reports' Crossref feed has its article.type set to "report".
        """
        doc = json_file_to_dict(self.get_resource_path('crossref-report-doc.json'))
        note_dict = self.engine.convert_to_notification(doc)
        assert note_dict['metadata']['article']['type'] == 'report'

    @app_decorator
    def test_monograph(self):
        """
        Test that a Notification created from a document harvested from the
        'Monographs' Crossref feed has its article.type set to "monograph".
        """
        doc = json_file_to_dict(self.get_resource_path('crossref-monograph-doc.json'))
        note_dict = self.engine.convert_to_notification(doc)
        assert note_dict['metadata']['article']['type'] == 'monograph'

    @app_decorator
    def test_posted_content_preprint(self):
        """
        Test that a Notification created from a document harvested from the
        'Posted Content' Crossref feed with a 'subtype' equal to 'preprint' has its article.type
        set to 'article-preprint'.
        """
        doc = json_file_to_dict(self.get_resource_path('crossref-posted-content-preprint-doc.json'))
        note_dict = self.engine.convert_to_notification(doc)
        assert note_dict['metadata']['article']['type'] == 'article-preprint'

    @app_decorator
    def test_posted_content_other(self):
        """
        Test that a Notification created from a document harvested from the
        'Posted Content' Crossref feed with a 'subtype' equal to 'other' has its article.type
        set to 'other'.
        """
        doc = json_file_to_dict(self.get_resource_path('crossref-posted-content-other-doc.json'))
        note_dict = self.engine.convert_to_notification(doc)
        assert note_dict['metadata']['article']['type'] == 'other'

    @app_decorator
    def test_proceedings_article(self):
        """
        Test that a Notification created from a document harvested from the
        'Proceedings Articles' Crossref feed with a 'subtype' equal to 'other' has its article.type
        set to 'proceedings'.
        """
        doc = json_file_to_dict(self.get_resource_path('crossref-proceedings-article-doc.json'))
        note_dict = self.engine.convert_to_notification(doc)
        assert note_dict['metadata']['article']['type'] == 'proceedings'

