import re
from lxml.etree import fromstring
from requests_mock import Mocker
from unittest import TestCase

from octopus.lib.data import dictionary_get
from octopus.lib.paths import get_real_path
from router.shared.models.note import IncomingNotification
from router.harvester.app import app, app_decorator
from router.harvester.engine.GetEngine import get_harvester_engine
from router.harvester.engine.QueryEngineElsevier import ElsevierIterator, QueryEngineElsevier, HarvestError
from tests.harvester_tests.test_engine.query_engine_test_base import QueryEngineTest


MOCK_SEARCH_URL = "mock://elsevier/search"
MOCK_ARTICLE_URL = "mock://elsevier/article"
MOCK_PAGED_SEARCH_URL = "mock://elsevier/paged"
MOCK_PAGED_ARTICLE_URL = "mock://elsevier/article-paged"

mock_search_missing_prism = {
    "search-results": {
        "opensearch:totalResults": "2",
        "opensearch:startIndex": "0",
        "link": [
            {
                "@ref": "last",
                "@href": "we won't touch this."
            },
        ],
        "entry": [
            {
                "@_fa": "true",
                "error": "Result set was empty"
            },
            {
                "@_fa": "true",
                "error": "Result set was empty"
            }
        ]
    }
}
mock_search = {
    "search-results": {
        "opensearch:totalResults": "2",
        "opensearch:startIndex": "0",
        "link": [
            {
                "@ref": "last",
                "@href": "we won't touch this."
            },
        ],
        "entry": [
            {
                "@_fa": "true",  # BAD entry
                "error": "Result set was empty"
            },
            {
                "@_fa": "true",
                "prism:url": MOCK_ARTICLE_URL
            }
        ]
    }
}

mock_search_with_next = {
    "search-results": {
        "opensearch:totalResults": "4",
        "opensearch:startIndex": "0",
        "link": [
            {
                "@ref": "next",
                "@href": MOCK_SEARCH_URL
            }
        ],
        "entry": [
            {
                "@_fa": "true",  # BAD entry
                "error": "Result set was empty"
            },
            {
                "@_fa": "true",
                "prism:url": MOCK_PAGED_ARTICLE_URL
            }
        ]
    }
}

# NOTE: This is all of the namespaces possible in a <jisc-retrieval-response>. Some of them aren't used,
# but they are kept as they are inside the XML namespace definition.
NAMESPACES = {
    "els": "http://www.elsevier.com/xml/elsapi/article/dtd",
    "bk": "http://www.elsevier.com/xml/bk/dtd",
    "cals": "http://www.elsevier.com/xml/common/cals/dtd",
    "ce": "http://www.elsevier.com/xml/common/dtd",
    "ja": "http://www.elsevier.com/xml/ja/dtd",
    "mml": "http://www.w3.org/1998/Math/MathML",
    "sa": "http://www.elsevier.com/xml/common/struct-aff/dtd",
    "sb": "http://www.elsevier.com/xml/common/struct-bib/dtd",
    "tb": "http://www.elsevier.com/xml/common/table/dtd",
    "xlink": "http://www.w3.org/1999/xlink",
    "xocs": "http://www.elsevier.com/xml/xocs/dtd",
    "dc": "http://purl.org/dc/elements/1.1/",
    "dcterms": "http://purl.org/dc/terms/",
    "prism": "http://prismstandard.org/namespaces/basic/2.0/",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance"
}

HARVESTER_ID = 99

def open_data_mock_file(filename):
    path = get_real_path(__file__, "..", "resources", filename)
    with open(path, "rb") as file_stream:
        return file_stream.read()


class TestElsevierIterator(TestCase):

    @app_decorator
    @Mocker()
    def test_iterator(self, m):
        """
        Simple test to see if given a search request, we'll iterate over the items in that search request.
        """
        m.get(re.compile(MOCK_SEARCH_URL), json=mock_search)
        m.get(MOCK_ARTICLE_URL, text="<jisc-retrieval-response></jisc-retrieval-response>")
        iterator = ElsevierIterator(MOCK_SEARCH_URL)
        for item in iterator:
            assert item.tag == "jisc-retrieval-response"

        assert iterator.total == 1
        assert iterator.missing_prism == 1
        assert iterator.empty_iterator()

    @app_decorator
    @Mocker()
    def test_iterator_with_pages(self, m):
        """
        Given a search request with a next page, make sure we iterate over both items.
        """
        m.get(re.compile(MOCK_SEARCH_URL), json=mock_search)
        m.get(re.compile(MOCK_PAGED_SEARCH_URL), json=mock_search_with_next)
        m.get(MOCK_ARTICLE_URL, text="<jisc-retrieval-response></jisc-retrieval-response>")
        m.get(MOCK_PAGED_ARTICLE_URL, text="<paged-retrieval-response></paged-retrieval-response>")
        iterator = ElsevierIterator(MOCK_PAGED_SEARCH_URL)
        items = list(iterator)
        assert len(items) == 2
        assert iterator.total == 2
        assert iterator.missing_prism == 2
        assert items[0].tag == "paged-retrieval-response"
        assert items[1].tag == "jisc-retrieval-response"
        assert iterator.empty_iterator()


class TestQueryEngineElsevier(QueryEngineTest):

    def test_process_author_group(self):
        """
        Make sure that when we have an author group, all the affiliations apply to every author, and that the author
        gets their list of email address identifiers and names.

        The misplaced comma on 'Some University..' is purposeful.
        For complex ce:textfn structures,
        it will put spaces between the comma if the content previous to the comma is an element rather than tex.

        Examples:
        <ce:textfn>
            Some
            <ce:italic>University</ce:italic>
            ,
            <ce:italic>United</ce:italic>
            ..
        </ce:textfn>
        - > Some University , United
        """
        etree = fromstring(open_data_mock_file("author_group.xml"))
        first_author, second_author = list(QueryEngineElsevier._process_author_group(etree, NAMESPACES))

        assert first_author.get("type") == "corresp"
        assert first_author.get("affiliations") == [
            {'raw': 'Some University , United Kingdom',
             'org': 'Some University',
             'street': '123 Random Street',
             'city': 'City A', 'country': 'United Kingdom', 'postcode': 'Post-code'}]
        assert dictionary_get(first_author, "name", "fullname") == "Person, Some"
        identifiers = first_author.get("identifier")
        # there are two identifiers in the input xml, but one doesn't have type attribute of value "email"-
        # so make sure only one gets returned
        assert len(identifiers) == 1

        email = identifiers[0]
        assert email.get("id") == "some@person.org"

        assert second_author.get("type") is None
        assert second_author.get("affiliations") == [
            {'raw': 'Some University , United Kingdom',
             'org': 'Some University',
             'street': '123 Random Street',
             'city': 'City A',
             'country': 'United Kingdom',
             'postcode': 'Post-code'
             },
            {'raw': 'University of Other, City B, United Kingdom',
             'org': 'University of Other',
             'city': 'City B',
             'country': 'United Kingdom'
             }]
        assert dictionary_get(second_author, "name", "fullname") == "Person, Other"
        identifiers = second_author.get("identifier")
        assert identifiers

        orcid = identifiers[0]
        assert orcid.get("id") == "0000-0001-0002-0003"

    def test_process_grants(self):
        """
        With a list of grant-sponsor elements and a list of grant-number elements, make sure the correct
        information is produced.
        """
        etree = fromstring(open_data_mock_file("grants_and_sponsors.xml"))
        sponsors = etree.findall("ce:grant-sponsor", namespaces=NAMESPACES)
        numbers = etree.findall("ce:grant-number", namespaces=NAMESPACES)

        grants_list = QueryEngineElsevier._process_grants(sponsors, numbers)

        assert grants_list[0] == {"name": "Commonwealth Scholarship Commission",
                                  "identifier": [{"type": "FundRef", "id": "https://doi.org/10.13039/501100000867"}],
                                  "grant_numbers": ["NGCN-2018-237"]
                                  }
        assert grants_list[1] == {"name": "A Sponsor", "grant_numbers": ["1", "2"]}
        assert grants_list[2] == {"name": "Other Sponsor", "grant_numbers": ["3"]}

    @app_decorator
    def test_full_doc(self):
        """
        Take a full elsevier document and test the other metadata elements we did not test in other tests
        """
        etree = fromstring(open_data_mock_file("elsevier_full.xml"))
        note_data = IncomingNotification(QueryEngineElsevier.convert_etree_to_incoming_notification(etree))

        assert note_data.publication_date == {"date": "2018-03-12", "publication_format": "electronic"}
        assert note_data.article_title == "Article Title"
        assert note_data.article_start_page == "257"
        assert note_data.article_end_page == "272"
        assert note_data.article_identifiers
        assert note_data.article_identifiers[0] == {"type": "doi", "id": "10.1016/j.erss.2018.01.019"}
        assert note_data.journal_title == "Journal Title"
        assert note_data.journal_volume == "40"
        assert note_data.journal_identifiers
        assert note_data.journal_identifiers[0] == {"id": "22146296", "type": "issn"}
        assert note_data.article_abstract == "The Abstract"
        assert note_data.article_version == "AM"
        assert note_data.publication_status == "Published"

        assert note_data.embargo_end == "2020-03-12"
        assert note_data.accepted_date == "2018-01-29"
        licenses = note_data.licenses
        assert licenses

    @app_decorator
    def test_open_access(self):
        # test that behaviour is different when article is specified to be open access
        # (this is the exact same doc as the full_doc, except with is_open_access attribute set to "1" instead of "0")
        etree = fromstring(open_data_mock_file("elsevier_full_open.xml"))
        note_data = IncomingNotification(QueryEngineElsevier.convert_etree_to_incoming_notification(etree))

        assert note_data.article_version == "VOR"
        assert note_data.embargo_end is None
        assert note_data.publication_status == "Published"

    @app_decorator
    def test_ignored_submission(self):
        # test that when item stage submitted is not one we are interested in, that we do not process the notification
        # (that None is returned from `convert_etree_to_incoming_notification`)
        etree = fromstring(open_data_mock_file("elsevier_ignored_item_stage.xml"))
        note_data = QueryEngineElsevier.convert_etree_to_incoming_notification(etree)

        assert note_data is None

    @Mocker()
    @app_decorator
    def test_all_missing_prism_urls(self, m):
        """
        Mock executing a simple search request that has bad 'entry' result set
        """
        m.get(re.compile(MOCK_SEARCH_URL), json=mock_search_missing_prism)

        query_engine = get_harvester_engine(app.config["ELSEVIER"], self.es_db, MOCK_SEARCH_URL, HARVESTER_ID, name_ws="Elsevier")
        query_engine.create_harvester_ix()
        with self.assertRaises(HarvestError) as exc:
            query_engine.execute()
        assert "All 2 search results were missing 'prism:url' elements" in str(exc.exception)

        query_engine.delete_harvester_ix()

    @Mocker()
    @app_decorator
    def test_execute_and_json_format(self, m):
        """
        Mock executing a simple search request, and make sure that convert_to_notification returns correct information.
        """
        m.get(re.compile(MOCK_SEARCH_URL), json=mock_search)
        m.get(MOCK_ARTICLE_URL, content=open_data_mock_file("elsevier_full.xml"))

        query_engine = get_harvester_engine(app.config["ELSEVIER"], self.es_db, MOCK_SEARCH_URL, HARVESTER_ID, name_ws="Elsevier")
        query_engine.create_harvester_ix()
        query_engine.execute()

        response = self.es_db.execute_search_query_scroll(query_engine.engine_index)
        assert response.get("total") == 1
        hits = response.get("hits")
        note_dict = query_engine.convert_to_notification(hits[0]["_source"])
        assert isinstance(note_dict, dict)
        assert note_dict["provider"]['route'] == "harv"
        assert note_dict["provider"]['agent'] == "Elsevier"
        note = IncomingNotification(note_dict)
        assert note.provider_route == "harv"
        assert note.provider_agent == "Elsevier"
        query_engine.delete_harvester_ix()

    @app_decorator
    def test_license_and_embargo(self):
        # set up a class with a text attribute which we can use in place of an Element during testing
        class TextAttribute:
            def __init__(self, val):
                self.text = val

            @property
            def text(self):
                return self._text

            @text.setter
            def text(self, val):
                self._text = val
        open_license_text = "creativecommons.org"
        open_license = TextAttribute(open_license_text)
        closed_license_text = "notopen.org"
        closed_license = TextAttribute(closed_license_text)
        start_date_text = "2018-01-01"
        start_date = TextAttribute(start_date_text)
        under_embargo_text = "This article is under embargo with an end date yet to be finalised."
        probably_under_embargo_text = "Probably under embargo with an end date yet to be finalised. Please refer to licence."
        endless_embargo_date = "9999-12-31"
        status_published = "Published"
        status_accepted = "Accepted"
        cc_by_nc_nd = "http://creativecommons.org/licenses/by-nc-nd/4.0/"

        def test_case(license, start_date, is_oa, pub_status, expected_license, expected_embargo_end):
            license, embargo_end = QueryEngineElsevier._calculate_license_and_embargo(license, start_date, is_oa, pub_status)
            assert license == expected_license
            assert embargo_end == expected_embargo_end

        # ------------------------------
        # Tests for GOLD access journals
        # ------------------------------

        # Test when we have an open licence and a start date, that we set the licensing info but NO embargo
        test_case(
            open_license,
            start_date,
            True,
            status_published,
            [{"url": open_license_text, "start": start_date_text}],
            None
        )
        # Test when we have an open licence and no start date, that we set licensing info but NO embargo
        test_case(
            open_license,
            None,
            True,
            status_accepted,
            [{"url": open_license_text}],
            None
        )

        # -------------------------------
        # Tests for SUBSCRIPTION journals
        # -------------------------------

        # Test when we have a start-date but NO licence and it is published,
        # then we set an embargo and CC BY-NC-ND licence is assumed
        test_case(
            None,
            start_date,
            False,
            status_published,
            [{"url": cc_by_nc_nd, "start": start_date_text}],
            start_date_text
        )

        # Test when we have a start-date but NO licence and it is NOT yet published,
        # then we set an endless embargo and ignore the licence
        test_case(
            None,
            start_date,
            False,
            status_accepted,
            [{"title": under_embargo_text}],
            endless_embargo_date
        )

        # Test when we have an open license and start date, that we set an embargo
        test_case(
            open_license,
            start_date,
            False,
            status_published,
            [{"url": open_license_text, "start": start_date_text}],
            start_date_text
        )
        
        # Test that when we have an open license and no start date, we ignore the license and set an endless embargo
        test_case(
            open_license,
            None,
            False,
            status_published,
            [{"title": under_embargo_text}],
            endless_embargo_date
        )
        
        
        # Test that when we have a closed license and a start date, we add an additional license to our list
        test_case(
            closed_license,
            start_date,
            False,
            status_published,
            [{"title": under_embargo_text}, {"url": closed_license_text, "start": start_date_text}],
            endless_embargo_date
        )

       # Test that when we have a closed license but no start date, we keep the existing license and set an endless
        # embargo with different title
        test_case(
            closed_license,
            None,
            False,
            status_accepted,
            [{"title": probably_under_embargo_text, "url": closed_license_text}],
            endless_embargo_date
        )

        # Test that when we have no licensing info at all, we just create a licence with an endless embargo
        test_case(
            None,
            None,
            False,
            status_accepted,
            [{"title": under_embargo_text}],
            endless_embargo_date
        )
