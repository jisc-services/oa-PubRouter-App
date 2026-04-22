
import json
from lxml import etree
from testfixtures import compare
from octopus.lib.paths import get_real_path
from octopus.modules.testing.compare import compare_dict_ignore_list_order

from router.harvester.app import app_decorator
from router.harvester.engine.QueryEnginePubMed import PubMedQueryEngine
from tests.harvester_tests.test_engine.query_engine_test_base import QueryEngineTest


def load_xml_from_file(filename):
    """
    Creates an XML structure from the content of a file provided

    :param filename: name of the file to extract the content from
    """
    path = get_real_path(__file__, "..", "resources", filename)
    tree = etree.parse(path)
    return tree.getroot()


AUTHORS_ONLY = '{"metadata": {"article": {"title": "The effects of prolonged exposure and sertraline on emotion regulation in individuals with posttraumatic stress disorder."}, "author": [{"affiliations": [{"raw": "Department of Psychology, University of Washington, Guthrie Hall, Box 351525, Seattle, WA 98195-1525, United States. Electronic address: aworly@u.washington.edu."}], "name": {"fullname": "Jerud, Alissa B", "surname": "Jerud", "firstname": "Alissa B"}}, {"affiliations": [{"raw": "Department of Psychology, University of Washington, Guthrie Hall, Box 351525, Seattle, WA 98195-1525, United States."}], "name": {"fullname": "Pruitt, Larry D", "surname": "Pruitt", "firstname": "Larry D"}}, {"affiliations": [{"raw": "Department of Psychology, University of Washington, Guthrie Hall, Box 351525, Seattle, WA 98195-1525, United States."}], "name": {"fullname": "Zoellner, Lori A", "surname": "Zoellner", "firstname": "Lori A"}}, {"affiliations": [{"raw": "Department of Psychological Sciences, Case Western Reserve University, Mather Memorial 103, 10900 Euclid Ave., Cleveland, OH 44106-7123, United States."}], "name": {"fullname": "Feeny, Norah C", "surname": "Feeny", "firstname": "Norah C"}}]}}'

GRANTS_ONLY = '{"metadata": {"article": {"title": "The effects of prolonged exposure and sertraline on emotion regulation in individuals with posttraumatic stress disorder."}, "funding": [{"grant_numbers": ["R01 MH066347", "R01 MH066348"], "name": "NIMH NIH HHS"}]}}'

TITLE_ONLY_AUTHOR_EMPTY = '{"metadata": {"article": {"title": "The effects of prolonged exposure and sertraline on emotion regulation in individuals with posttraumatic stress disorder."}}}'

TITLE_ONLY = '{"metadata": {"article": {"title": "The effects of prolonged exposure and sertraline on emotion regulation in individuals with posttraumatic stress disorder."}}}'

ROOT_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"

HARVESTER_ID = 'test_pubmed'

class PubMedQueryEngineTest(QueryEngineTest):
    def setUp(self):
        # sleep(0.5)    # Avoid too frequent calls to ROOT_URL
        pass

    @app_decorator
    def test_retrieve_doc_pubmed(self):
        self.logger.info("Test retrieve doc PubMed")
        url = ROOT_URL + "esearch.fcgi?db=pubmed&term=1873-622X&mindate=2016/01/01&maxdate=2016/01/02"
        query_engine = PubMedQueryEngine(self.es_db, url, HARVESTER_ID, self.date_today, self.date_today, self.config["PUBMED"])
        query_engine.delete_harvester_ix()
        query_engine.create_harvester_ix()
        total = query_engine.execute()
        self.assertEqual(total, 1)

    @app_decorator
    def test_retrieve_no_docs_pubmed(self):
        self.logger.info("Test retrieve no docs from PubMed")
        url = ROOT_URL + "esearch.fcgi?db=pubmed&term=187XXXX22X&mindate=2016/01/01&maxdate=2016/01/02"
        query_engine = PubMedQueryEngine(self.es_db, url, HARVESTER_ID, self.date_today, self.date_today, self.config["PUBMED"])
        query_engine.delete_harvester_ix()
        query_engine.create_harvester_ix()
        total = query_engine.execute()
        self.assertEqual(total, 0)

    @app_decorator
    def test_convert2json(self):
        self.logger.info("Test convert to JSON")
        pubmed_dict = {'metadata': {'article': {'title': 'Applying new evidence standards to youth cognitive behavioral therapies - A review.', 'abstract': 'This review included 136 published randomized controlled trials (RCTs) of youth cognitive behavioral therapy (CBT) treatments. We aimed to test the premise that evidence-based youth treatments can be better differentiated from each other by applying more nuanced standards of evidence. Accordingly, we applied three standards to this article sample to determine how many treatments produced significant results: (a) on multiple target symptom measures, (b) at follow-up, and/or (c) against an active comparison group. We identified how many trials met standards individually and in combination. Although 87 of the 136 articles produced at least one significant treatment result at post-assessment, the subsets of "passing" articles were smaller and varied for any one of our three standards, with only 11 articles (8%) meeting all three standards simultaneously. Implications are discussed regarding the definition of "evidence-based," the need for multi-parameter filtering in treatment selection and clinical decision making, and future directions for research. We ultimately argue the value in assessing youth treatments for different types of evidence, which is better achieved through dynamic sets of standards, rather than a single approach to assessing general strength of evidence.  [Abstract copyright: Copyright © 2016 Elsevier Ltd. All rights reserved.]', 'language': ['eng'], 'type': 'journal article; review', 'subject': ['Treatment Outcome', 'Youth', 'Mental Disorders - therapy', 'Randomized Controlled Trials as Topic - standards', 'Standards', 'Age Factors', 'Cognitive Behavioral Therapy', 'Anxiety', 'Evidence-based', 'CBT', 'Treatment selection', 'Humans'], 'page_range': '147-158', 'e_num': 'S0005-7967(16)30231-5', 'identifier': [{'id': '28061375', 'type': 'pubmed'}, {'id': 'S0005-7967(16)30231-5', 'type': 'pii'}, {'id': '10.1016/j.brat.2016.12.011', 'type': 'doi'}]}, 'journal': {'title': 'Behaviour research and therapy', 'identifier': [{'id': '1873-622X', 'type': 'eissn'}], 'volume': '90'}, 'publication_date': {'year': '2016', 'month': '12', 'day': '23', 'date': '2016-12-23', 'publication_format': 'electronic'}, 'publication_status': 'ppublish', 'author': [{'name': {'fullname': 'Rith-Najarian, Leslie R', 'surname': 'Rith-Najarian', 'firstname': 'Leslie R'}, 'affiliations': [{'raw': 'Department of Psychology, University of California, Los Angeles 1285 Franz Hall, Los Angeles, CA, 90095, USA. Electronic address: leslierrn@ucla.edu.'}]}, {'name': {'fullname': 'Park, Alayna L', 'surname': 'Park', 'firstname': 'Alayna L'}, 'affiliations': [{'raw': 'Department of Psychology, University of California, Los Angeles 1285 Franz Hall, Los Angeles, CA, 90095, USA.'}]}, {'name': {'fullname': 'Wang, Tina', 'surname': 'Wang', 'firstname': 'Tina'}, 'affiliations': [{'raw': 'Department of Psychology, University of California, Los Angeles 1285 Franz Hall, Los Angeles, CA, 90095, USA.'}]}, {'name': {'fullname': 'Etchison, Ana I', 'surname': 'Etchison', 'firstname': 'Ana I'}, 'affiliations': [{'raw': 'Department of Psychology, University of California, Los Angeles 1285 Franz Hall, Los Angeles, CA, 90095, USA.'}]}, {'name': {'fullname': 'Chavira, Denise A', 'surname': 'Chavira', 'firstname': 'Denise A'}, 'affiliations': [{'raw': 'Department of Psychology, University of California, Los Angeles 1285 Franz Hall, Los Angeles, CA, 90095, USA.'}]}, {'name': {'fullname': 'Chorpita, Bruce F', 'surname': 'Chorpita', 'firstname': 'Bruce F'}, 'affiliations': [{'raw': 'Department of Psychology, University of California, Los Angeles 1285 Franz Hall, Los Angeles, CA, 90095, USA.'}]}], 'history_date': [{'date_type': 'received', 'date': '2016-02-02'}, {'date_type': 'revised', 'date': '2016-11-11'}, {'date_type': 'accepted', 'date': '2016-12-16'}], 'accepted_date': '2016-12-16'}}
        xml_doc = load_xml_from_file("PubMed.xml")
        doc_from_xml = PubMedQueryEngine.xml2json(xml_doc.find("PubmedArticle"))
        dict_from_xml = json.loads(doc_from_xml.replace('\u00a9', ''))
        self.assertIsInstance(dict_from_xml, dict)
        self.assertTrue(compare_dict_ignore_list_order(dict_from_xml, pubmed_dict))
        # compare(dict_from_xml, pubmed_dict)

    def test_convert2json_authors(self):
        self.logger.info("Test convert to JSON authors only")
        xml_doc = load_xml_from_file("PubMedAuthorsOnly.xml")
        doc_from_xml = PubMedQueryEngine.xml2json(xml_doc.find("PubmedArticle"))

        # self.assertTrue(compare_dict_ignore_list_order(json.loads(doc_from_xml), json.loads(AUTHORS_ONLY)))
        compare(json.loads(doc_from_xml), json.loads(AUTHORS_ONLY))

    def test_convert2json_grants(self):
        self.logger.info("Test convert to JSON grants only")
        xml_doc = load_xml_from_file("PubMedGrantsOnly.xml")
        doc_from_xml = PubMedQueryEngine.xml2json(xml_doc.find("PubmedArticle"))
        # self.assertTrue(compare_dict_ignore_list_order(json.loads(doc_from_xml), json.loads(GRANTS_ONLY)))
        compare(json.loads(doc_from_xml), json.loads(GRANTS_ONLY))

    @app_decorator
    def test_no_data(self):
        self.logger.info("Test no data")
        url = ROOT_URL + "esearch.fcgi?db=pubmed&term=1873-6b22X&mindate={start_date}&maxdate={end_date}"
        query_engine = PubMedQueryEngine(self.es_db, url, HARVESTER_ID, self.date_today, self.date_today, self.config["PUBMED"])
        query_engine.delete_harvester_ix()
        query_engine.create_harvester_ix()
        total = query_engine.execute()
        self.assertEqual(total, 0)

    @app_decorator
    def test_valid_invalid_url(self):
        self.logger.info("Test valid and invalid url")
        url = ROOT_URL + "esearch.fcgi?db=pubmed&mindate={start_date}&maxdate={end_date}"
        self.assertTrue(PubMedQueryEngine.is_valid(url))

        url = "invalid"
        self.assertFalse(PubMedQueryEngine.is_valid(url))

    def test_empty_author(self):
        self.logger.info("Test empty author")
        xml_doc = load_xml_from_file("PubMedEmptyAuthor.xml")
        doc_from_xml = PubMedQueryEngine.xml2json(xml_doc.find("PubmedArticle"))
        # self.assertTrue(compare_dict_ignore_list_order(json.loads(doc_from_xml), json.loads(TITLE_ONLY_AUTHOR_EMPTY)))
        compare(json.loads(doc_from_xml), json.loads(TITLE_ONLY_AUTHOR_EMPTY))

    def test_empty_grant(self):
        self.logger.info("Test empty grant")
        xml_doc = load_xml_from_file("PubMedEmptyGrant.xml")
        doc_from_xml = PubMedQueryEngine.xml2json(xml_doc.find("PubmedArticle"))
        # self.assertTrue(compare_dict_ignore_list_order(json.loads(doc_from_xml), json.loads(TITLE_ONLY)))
        compare(json.loads(doc_from_xml), json.loads(TITLE_ONLY))

    def test_empty_date(self):
        self.logger.info("Test empty date")
        xml_doc = load_xml_from_file("PubMedEmptyDate.xml")
        doc_from_xml = PubMedQueryEngine.xml2json(xml_doc.find("PubmedArticle"))
        # self.assertTrue(compare_dict_ignore_list_order(json.loads(doc_from_xml), json.loads(TITLE_ONLY)))
        compare(json.loads(doc_from_xml), json.loads(TITLE_ONLY))

    @app_decorator
    def test_article_date_and_format(self):
        self.logger.info("Test article date")
        xml_doc = load_xml_from_file("PubMedFull.xml")
        doc_from_xml = json.loads(PubMedQueryEngine.xml2json(xml_doc.find("PubmedArticle")))
        pub_date = doc_from_xml["metadata"]["publication_date"]
        self.assertEqual("2015-12-10", pub_date["date"])
        self.assertEqual("electronic", pub_date["publication_format"])
         # Remove article date and try again
        article_date = xml_doc.xpath("//ArticleDate")[0]
        article_date.getparent().remove(article_date)
        doc_from_xml = json.loads(PubMedQueryEngine.xml2json(xml_doc.find("PubmedArticle")))
        pub_date = doc_from_xml["metadata"]["publication_date"]
        self.assertEqual("2016-02-01", pub_date["date"])
        self.assertEqual("print", pub_date["publication_format"])

    @app_decorator
    def test_full_doc(self):
        self.logger.info("Test full doc")
        xml_doc = load_xml_from_file("PubMedFull.xml")
        url = ROOT_URL + "esearch.fcgi?db=pubmed&term=1873-622X&mindate=2016/01/01&maxdate=2016/01/02"
        query_engine = PubMedQueryEngine(self.es_db, url, HARVESTER_ID, self.date_today, self.date_today, self.config["PUBMED"])
        doc_from_xml = query_engine.xml2json(xml_doc.find("PubmedArticle"))
        notification_dict = query_engine.convert_to_notification(json.loads(doc_from_xml))
        self.assertIsInstance(notification_dict, dict)
        metadata_article = notification_dict.get("metadata").get("article")
        # Check that start-page value is present, and that elocation-id, which has the same value, is NOT captured as e_num
        expected_start_pg = "S122"
        self.assertEqual(metadata_article.get("start_page"), expected_start_pg)
        for eloc_el in xml_doc.findall(".//ELocationID"):
            if eloc_el.get("EIdType") == "pii":
                self.assertEqual(eloc_el.text, expected_start_pg)      # Start page number is used in ElocationID
        self.assertIsNone(metadata_article.get("e_num"))    # ElocationID not captured

    @app_decorator
    def test_temp_records_doc_pubmed(self):
        self.logger.info("Test Temporary records of PubMed")

        # insert a PubMed record
        url = ROOT_URL + "esearch.fcgi?db=pubmed&term=1873-622X&mindate=2016/01/01&maxdate=2016/01/02"
        query_engine = PubMedQueryEngine(self.es_db, url, HARVESTER_ID, self.date_today, self.date_today, self.config["PUBMED"])
        query_engine.delete_harvester_ix()
        query_engine.create_harvester_ix()
        total = query_engine.execute()

        result = self.es_db.execute_search_query_scroll(query_engine.engine_index, self.config["MATCH_ALL"])
        self.assertEqual(total, result['total'])

        # Delete ONLY PubMed records in Temporary table and check that there are no records
        result = query_engine.delete_harvester_index_recs()
        self.assertEqual(1, result['deleted'])

        # check the result
        result = self.es_db.execute_search_query_scroll(query_engine.engine_index, self.config["MATCH_ALL"])
        self.assertEqual(0, result['total'])
