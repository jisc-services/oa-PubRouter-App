"""
Tests on the various xwalks

Uses ../resources/outgoing.json as an example outgoing notification, then processes this using
the various different xwalks and compares the output to the model outputs:
    dspace_expected.xml,
    dspace_rioxx_expected.xml,
    eprints_expected.xml,
    rioxx_expected.xml

Tests rely on the model outputs being in the same order as the respective xwalk produces. Bare this
in mind when making changes.
"""


import json
import codecs
from lxml import etree
from datetime import datetime, timedelta
from copy import deepcopy
from router.jper_sword_out.app import app_decorator, app
from unittest import TestCase

app.config["LOGFILE"] = "/tmp/sword-out-tests.log"

from octopus.lib.paths import get_real_path
from octopus.core import initialise
from router.shared.models.note import RoutedNotification, OutgoingNotification
from router.jper_sword_out import xwalk


def compare_etrees(expected_xml, calc_xml):
    """
    Compare 2 XML etree objects to see whether they are identical.

    :param expected_xml: Expected XML etree
    :param calc_xml:    Calculate XML etree
    :return: nothing (assertion is made within the function)
    """

    def _compare_formatted_xml(expected_xml_pretty, calc_xml_pretty):
        """
        Compare two XML strings, each of which is formatted with one element per line, to determine whether the XML is 
        essentially identical. Identical means that each has the same number of elements, in the same order, with the 
        same content and attribute values.  However, attributes within an element CAN be ordered differently.
        
        :param expected_xml_pretty: string - expected XML formatted one element per line
        :param calc_xml_pretty: string - calculated XML formatted one element per line
        :return: Error string - empty string means OK
        """
        def _err_str(msg, x):
            return f"The calculated & expected XML {msg} at Line {x}."


        # Split formatted XML into list of elements
        expected_xml_elements = expected_xml_pretty.split("\n")
        calculated_xml_elements = calc_xml_pretty.split("\n")
        len_expected = len(expected_xml_elements)
        len_calc = len(calculated_xml_elements)
        if len_calc != len_expected:
            return "The calculated & expected XML have a different number of lines."

        # Compare expected and calculated XML one line at a time
        for x in range(0, len_calc):
            line_expected = expected_xml_elements[x]
            line_calc = calculated_xml_elements[x]
            # Lines match
            if line_calc == line_expected:
                continue

            # Lines don't exactly match. Note that it may be because attributes are in different order (which is acceptible)
            
            # Make sure lines are same length
            if len(line_calc) != len(line_expected):
                return _err_str("have different line lengths", x)

            # split each line, which looks something like "<element attr1="xxx" attr2="yyy">something</element>" or
            # <empty_element attr="x"/> on the first occurence of ">" or "/>"
            partition_string = "/>" if "/>" in line_expected else ">"
            head_expected, crud, tail_expected = line_expected.strip().partition(partition_string)
            head_calc, crud, tail_calc = line_calc.strip().partition(partition_string)
            
            # The tails should match
            if tail_calc != tail_expected:
                return _err_str("differ", x)

            # Now convert each head into a list, splitting at each space
            head_expected_parts = head_expected.split()
            head_calc_parts = head_calc.split()

            # The first item in each list (e.g. something like "<element") should match
            # They are "popped" to remove them from the list for comparison
            if head_expected_parts.pop(0) != head_calc_parts.pop(0):
                return _err_str("have different Element Names", x)

            # Sort remaining element in each list (so attributes are now in same order) and compare
            head_expected_parts.sort()
            head_calc_parts.sort()
            if head_calc_parts != head_expected_parts:
                return _err_str("have different element Attributes", x)

        return ""

    def _etree_to_normalised_formatted_xml_str(etree_xml):
        """
        Convert an etree XML structure into a "normalised" pretty-printed (i.e. 1 element per line) XML string

        :param etree_xml:   XML etree object
        :return: string - formatted XML string
        """
        # Have to specify "html" to ensure that empty elements are handled similarly for all etrees
        xml_str = etree.tostring(etree_xml, encoding="unicode", method="html")

        # Now convert the "HTML" form back into etree, and then create pretty-printed XML string
        return etree.tostring(etree.fromstring(xml_str), encoding="unicode", method="xml", pretty_print=True)

    expected_xml_string = _etree_to_normalised_formatted_xml_str(expected_xml)
    calc_xml_string = _etree_to_normalised_formatted_xml_str(calc_xml)

    err_msg = _compare_formatted_xml(expected_xml_string, calc_xml_string)
    if err_msg:
        print(f"\nERROR:\n*** {err_msg}\n")
        print("EXPECTED:\n", expected_xml_string)
        print("CALCUL'D:\n", calc_xml_string)
        assert False, err_msg
    else:
        assert True


# takes a file path and returns the JSON object found at that path as a dictionary
def file_to_json(file_location):
    with codecs.open(file_location, 'r', "utf-8") as json_file:
        returned_json = json.loads(json_file.read())
    return returned_json


class TestXwalk(TestCase):

    @classmethod
    def get_resource_path(cls, resource_name):
        return get_real_path(__file__, "..", "resources", resource_name)

    @classmethod
    @app_decorator
    def setUpClass(cls):
        super(TestXwalk, cls).setUpClass()
        initialise()
        cls._test_note = OutgoingNotification(file_to_json(cls.get_resource_path("outgoing.json")))

    @app_decorator
    def setUp(self):
        self.test_note = deepcopy(self._test_note)
        super().setUp()

    @app_decorator
    def tearDown(self):
        super().tearDown()

    @app_decorator
    def test_eprints_vanilla(self):
        # compares an eprints model output to a processed outgoing notification
        # process the notification
        eprints_entry = xwalk.eprints_xml_entry(self.test_note).xml
        eprints_expected = etree.parse(self.get_resource_path("eprints_expected.xml"))

        # compare the two etrees as strings
        compare_etrees(eprints_expected, eprints_entry)

    @app_decorator
    def test_dspace_vanilla(self):
        # compares a dspace model output to a processed outgoing notification
        # process the notification
        dspace_entry = xwalk.dspace_xml_entry(self.test_note).xml
        dspace_expected = etree.parse(self.get_resource_path("dspace_expected.xml"))
        # compare the two etrees as strings
        compare_etrees(dspace_expected, dspace_entry)

    @app_decorator
    def test_eprints_rioxx(self):
        # compares a rioxx model output to a processed outgoing notification
        # process the notification
        rioxx_entry = xwalk.eprints_rioxx_entry(self.test_note).xml
        rioxx_expected = etree.parse(self.get_resource_path("eprints_rioxx_expected.xml"))
        compare_etrees(rioxx_expected, rioxx_entry)

        def get_eprints_rioxx_page_range_from_converted_note():
            rioxx_entry = xwalk.eprints_rioxx_entry(self.test_note)
            eprints_page_range_el = rioxx_entry.xml.find("{http://pubrouter.jisc.ac.uk/rioxxplus/v2.0/}page_range")
            return eprints_page_range_el.text

        assert get_eprints_rioxx_page_range_from_converted_note() == "Page-range"

        # If no explicit page-range, confirm page-range created from start & end page values
        self.test_note.article_page_range = ""
        assert get_eprints_rioxx_page_range_from_converted_note() == "Start-pg–End-pg"
        self.test_note.article_end_page = ""
        assert get_eprints_rioxx_page_range_from_converted_note() == "Start-pg"
        self.test_note.article_start_page = ""
        # Check that page-range is constructed from e-num value if none of start-page, end-page or page-range are set
        assert get_eprints_rioxx_page_range_from_converted_note() == "e-Location"


    @app_decorator
    def test_original_eprints_rioxx(self):
        # compares a rioxx model output to a processed outgoing notification
        # process the notification
        rioxx_entry = xwalk.eprints_rioxx_entry(self.test_note, False).xml
        rioxx_expected = etree.parse(self.get_resource_path("eprints_rioxx_expected_original.xml"))

        compare_etrees(rioxx_expected, rioxx_entry)

    @app_decorator
    def test_dspace_rioxx(self):
        rioxx_entry = xwalk.dspace_rioxx_entry(self.test_note).xml
        rioxx_expected = etree.parse(self.get_resource_path("dspace_rioxx_expected.xml"))
        compare_etrees(rioxx_expected, rioxx_entry)

    @app_decorator
    def test_dspace_rioxx_embargo_date_in_the_past(self):
        # Embargo date in the past should not be included in output XML
        # test_note = OutgoingNotification(hard_notification)
        # Set embargo date to be in the past
        self.test_note.set_embargo(start="2015-01-01", end="2016-01-01", duration="12")
        rioxx_entry = xwalk.dspace_rioxx_entry(self.test_note).xml

        # Get expected DSpace RIOXX XML and remove the embargo element
        rioxx_expected = etree.parse(self.get_resource_path("dspace_rioxx_expected.xml"))
        embargo_el = rioxx_expected.find("{http://pubrouter.jisc.ac.uk/dspacerioxx/}embargo_date")
        if embargo_el is not None:
            rioxx_expected.getroot().remove(embargo_el)
        compare_etrees(rioxx_expected, rioxx_entry)

    def test_best_email_index(self):
        # tests xwalk best licenses method
        # check that .ac.uk always takes precedent
        emails = ["hello@example.com", "notasgood@hello.edu", "thebest@best.ac.uk"]
        assert xwalk._best_email_list(emails) == ["thebest@best.ac.uk", "hello@example.com", "notasgood@hello.edu"]
        # check that .edu is best when there is no .ac.uk
        emails = ["hello@example.com", "hello2@example.gov.uk", "thebest@best.edu"]
        assert xwalk._best_email_list(emails) == ["thebest@best.edu", "hello@example.com", "hello2@example.gov.uk"]
        # check that .gov.uk is best only compared to plain emails
        emails = ["hello@example.com", "best@best.gov.uk"]
        assert xwalk._best_email_list(emails) == ["best@best.gov.uk", "hello@example.com"]
        # check that defaults to 0 if no best found
        emails = ["hello@example.com", "hello2@example.com"]
        assert xwalk._best_email_list(emails) == emails

    @app_decorator
    def test_best_license(self):
        # tests the best_license method

        today = datetime.today()

        def _days_from_today_formatter(days_from_today):
            # takes a distance in days from today, and returns that date output in YYYY-MM-DD format
            return (today + timedelta(days_from_today)).strftime("%Y-%m-%d")

        late_past_date = _days_from_today_formatter(-150)
        later_past_date = _days_from_today_formatter(-100)
        early_past_date = _days_from_today_formatter(-300)
        early_future_date = _days_from_today_formatter(150)
        late_future_date = _days_from_today_formatter(300)
        today_date = _days_from_today_formatter(0)

        # some example licenses
        open_license_url = "creativecommons.org"
        closed_license_url = "notopen.org"
        open_license_no_start = {"url": open_license_url}
        open_license_early_past_start = {"url": open_license_url, "start": early_past_date}
        open_license_late_past_start = {"url": open_license_url, "start": late_past_date}
        open_license_early_future_start = {"url": open_license_url, "start": early_future_date}
        open_license_late_future_start = {"url": open_license_url, "start": late_future_date}
        open_license_today_start = {"url": open_license_url, "start": today_date}
        closed_license_no_start = {"url": closed_license_url}
        closed_license_early_past_start = {"url": closed_license_url, "start": early_past_date}
        closed_license_late_past_start = {"url": closed_license_url, "start": late_past_date}
        closed_license_early_future_start = {"url": closed_license_url, "start": early_future_date}
        closed_license_late_future_start = {"url": closed_license_url, "start": late_future_date}
        license_no_url_later_past_start = {"type": "ccby",  "start": later_past_date}
        license_no_url_early_future_start = {"type": "cc-by-nc",  "start": early_future_date}

        def _best_license_test(licenses, expected_best_license):
            # sorts licenses by start date (as is expected of the _best_license() function) - and tests the licenses
            # against the expected best license value
            routed_note = RoutedNotification()
            routed_note.licenses = licenses
            note = routed_note.make_outgoing()
            entry = xwalk.eprints_rioxx_entry(note)
            license_ref = entry.get_element("ali:license_ref")
            if license_ref is None:
                assert expected_best_license is None
            else:
                assert expected_best_license.get("url") == license_ref.text
                assert expected_best_license.get("start") == license_ref.attrib.get("start_date")

        # check that open licenses always take priority
        _best_license_test(
            [open_license_early_future_start, closed_license_early_past_start],
            open_license_early_future_start
        )
        # check that the latest open past start date always takes priority (where it has a URL)
        _best_license_test(
            [open_license_early_future_start, open_license_late_past_start, open_license_early_past_start,
             license_no_url_later_past_start],
            open_license_late_past_start
        )
        # check that the latest closed past start date always takes priority (if all licenses are closed) where it has URL
        _best_license_test(
            [closed_license_early_future_start, closed_license_late_past_start, closed_license_early_past_start,
             license_no_url_later_past_start],
            closed_license_late_past_start
        )
        # check that the earliest future date always takes priority
        _best_license_test(
            [open_license_late_future_start, open_license_early_future_start],
            open_license_early_future_start
        )
        # check that when we only have closed licenses, the earliest future date always takes priority
        _best_license_test(
            [closed_license_late_future_start, closed_license_early_future_start],
            closed_license_early_future_start
        )
        # check that no start date license takes priority over future starts
        _best_license_test(
            [open_license_late_future_start, open_license_early_future_start, open_license_no_start],
            open_license_no_start
        )
        # check that when we only have closed licenses, then no start date license takes priority over future ones
        _best_license_test(
            [closed_license_early_future_start, closed_license_late_future_start, closed_license_no_start],
            closed_license_no_start
        )
        # check that when we have multiple empty start dates things work as expected
        _best_license_test(
            [open_license_no_start, open_license_no_start],
            open_license_no_start
        )
        # check that a license starting today takes precedent over any other license
        _best_license_test(
            [open_license_early_past_start, open_license_late_past_start, open_license_no_start, open_license_today_start],
            open_license_today_start
        )

        # check with just one Open license
        _best_license_test(
            [open_license_late_future_start],
            open_license_late_future_start
        )

        # check with just one Closed license
        _best_license_test(
            [closed_license_early_past_start],
            closed_license_early_past_start
        )

        # check with just one Open license and one without a URL
        _best_license_test(
            [open_license_late_future_start, license_no_url_later_past_start],
            open_license_late_future_start
        )

        # check with just one Closed license and one without a URL
        _best_license_test(
            [closed_license_early_past_start, license_no_url_early_future_start],
            closed_license_early_past_start
        )

        # with 2 licenses, neither with a URL - expect no best-license
        _best_license_test(
            [license_no_url_later_past_start, license_no_url_early_future_start],
            None
        )

        # with 1 license without a URL - expect no best-license
        _best_license_test(
            [license_no_url_later_past_start],
            None
        )

        # with No licenses - expect no best-license
        _best_license_test(
            [],
            None
        )


class TestXWalkCrossrefEprintsRioxx(TestCase):
    """
    Test that EPrints-RIOXX XML is generated correctly from notifications created by the
    separate Crossref feeds (book-chapters, journal-article, monographs, posted-content,
    proceedings,  reports).
    """

    @classmethod
    def get_resource_path(cls, resource_name):
        return get_real_path(__file__, "..", "resources", "crossref_eprints_rioxx", resource_name)

    @classmethod
    @app_decorator
    def setUpClass(cls):
        super(TestXWalkCrossrefEprintsRioxx, cls).setUpClass()

    @app_decorator
    def setUp(self):
        initialise()
        super().setUp()

    @app_decorator
    def tearDown(self):
        super().tearDown()

    @app_decorator
    def test_book_chapter_notification_xml(self):
        """
        Test that the correct EPrints-RIOXX XML is generated from notification harvested from the
        'Crossref Book
        Chapters' feed.
        """
        hard_notification = file_to_json(self.get_resource_path('book-chapter.json'))
        self.test_note = OutgoingNotification(hard_notification)
        rioxx_expected = etree.parse(self.get_resource_path("book-chapter.xml"))
        rioxx_entry = xwalk.eprints_rioxx_entry(self.test_note).xml
        compare_etrees(rioxx_expected, rioxx_entry)

    @app_decorator
    def test_journal_article_notification_xml(self):
        """
        Test that the correct EPrints-RIOXX XML is generated from a notification harvested from the
        'Crossref Journal Articles' feed.
        """
        hard_notification = file_to_json(self.get_resource_path('journal-article.json'))
        self.test_note = OutgoingNotification(hard_notification)
        rioxx_expected = etree.parse(self.get_resource_path("journal-article.xml"))
        rioxx_entry = xwalk.eprints_rioxx_entry(self.test_note).xml
        compare_etrees(rioxx_expected, rioxx_entry)

    @app_decorator
    def test_monograph_notification_xml(self):
        """
        Test that the correct EPrints-RIOXX XML is generated from a notification harvested from the
        'Crossref Monographs' feed.
        """
        hard_notification = file_to_json(self.get_resource_path('monograph.json'))
        self.test_note = OutgoingNotification(hard_notification)
        rioxx_expected = etree.parse(self.get_resource_path("monograph.xml"))
        rioxx_entry = xwalk.eprints_rioxx_entry(self.test_note).xml
        compare_etrees(rioxx_expected, rioxx_entry)

    @app_decorator
    def test_reports_notification_xml(self):
        """
        Test that the correct EPrints-RIOXX XML is generated from a notification harvested from the
        'Crossref Reports' feed.
        """
        hard_notification = file_to_json(self.get_resource_path('report.json'))
        self.test_note = OutgoingNotification(hard_notification)
        rioxx_expected = etree.parse(self.get_resource_path("report.xml"))
        rioxx_entry = xwalk.eprints_rioxx_entry(self.test_note).xml
        compare_etrees(rioxx_expected, rioxx_entry)

    @app_decorator
    def test_posted_content_notification_xml_preprint(self):
        """
        Test that the correct EPrints-RIOXX XML is generated from a notification harvested from the
        'Crossref Posted Content' feed from a record with 'subtype' equal to 'preprint'.
        """
        hard_notification = file_to_json(self.get_resource_path('posted-content-preprint.json'))
        self.test_note = OutgoingNotification(hard_notification)
        rioxx_expected = etree.parse(self.get_resource_path("posted-content-preprint.xml"))
        rioxx_entry = xwalk.eprints_rioxx_entry(self.test_note).xml
        compare_etrees(rioxx_expected, rioxx_entry)

    @app_decorator
    def test_posted_content_notification_xml_other(self):
        """
        Test that the correct EPrints-RIOXX XML is generated from a notification harvested from the
        'Crossref Posted Content' feed from a record with 'subtype' equal to 'other'.
        """
        hard_notification = file_to_json(self.get_resource_path('posted-content-other.json'))
        self.test_note = OutgoingNotification(hard_notification)
        rioxx_expected = etree.parse(self.get_resource_path("posted-content-other.xml"))
        rioxx_entry = xwalk.eprints_rioxx_entry(self.test_note).xml
        compare_etrees(rioxx_expected, rioxx_entry)

    @app_decorator
    def test_proceedings_article_notification_xml(self):
        """
        Test that the correct EPrints-RIOXX XML is generated from a notification harvested from the
        'Crossref Proceedings Articles' feed.
        """
        hard_notification = file_to_json(self.get_resource_path('proceedings-article.json'))
        self.test_note = OutgoingNotification(hard_notification)
        rioxx_expected = etree.parse(self.get_resource_path("proceedings-article.xml"))
        rioxx_entry = xwalk.eprints_rioxx_entry(self.test_note).xml
        compare_etrees(rioxx_expected, rioxx_entry)
