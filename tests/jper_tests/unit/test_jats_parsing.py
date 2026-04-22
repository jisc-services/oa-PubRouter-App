"""
Acceptance/unit tests for parsing the following JATS entities:
 - Abstracts
 - Licenses
 - Publication date
 - Contributors
 - Funders
 - Affiliations

"""
from copy import deepcopy
from unittest import TestCase
from tests.jper_tests.fixtures.models import JATSFactory
from router.jper.models.jats import InvalidJATSError, JATS

class TestJATSParsing(TestCase):

    def setUp(self):
        super().setUp()
        print("\n****", self._testMethodName, "****\n")

    ### Testing ABSTRACT extraction ###
    
    def _jats_with_abstract(self, abstract_types_list=None, remove_original_abstract=False, expected=None):
        """
        Sets self.jats to have specified abstract elements. Returns expected abstract text.
        :param abstract_types_list: list of abstract types
        :param remove_original_abstract: Bool indicator determines whether original abstract is to be removed
        :param expected: Sub-string which is expected to prepend " Abstract:" in retrieved abstract string
        :return: Expected abstract string
        """

        # This is the expected string corresponding to the existing <abstract> element
        abstract_str = "Abstract: An analysis of the angular distribution of the decay Λb0 → Λμ+μ− is presented, using data collected with the LHCb detector between 2011 and 2016 and corresponding to an integrated luminosity of approximately 5 fb−1. Angular observables are determined using a moment analysis of the angular distribution at low hadronic recoil, corresponding to the dimuon invariant mass squared range 15 < q2 < 20 GeV2/c4. The full basis of observables is measured for the first time. The lepton-side, hadron-side and combined forward-backward asymmetries of the decay are determined to beAFBℓ=−0.39±0.04stat±0.01syst, AFBh=−0.30±0.05stat±0.02syst, AFBℓh=+0.25±0.04stat±0.01syst. The measurements are consistent with Standard Model predictions."

        # initialise jats
        self.jats = JATSFactory.jats_general()

        # Find the existing abstract element
        abstract = self.jats.xml_article_meta.find("./abstract")

        # If any abstract-type attributes are specified, create a series of elements with these
        if abstract_types_list:
            for abstract_type in abstract_types_list:
                # The new abstract element will be modelled on the original
                new_abstract = deepcopy(abstract)
                # Set abstract-type attribute
                new_abstract.set("abstract-type", abstract_type)
                title = new_abstract.find("title")
                # modify the (first) title text, by prepending with upper-case abstract type
                title.text = abstract_type.upper() + " " + title.text
                # Add new abstract element to the end of the article_meta
                self.jats.xml_article_meta.append(new_abstract)

        if remove_original_abstract:
            self.jats.xml_article_meta.remove(abstract)

        # Return the expected string version of the abstract
        return abstract_str if expected is None else abstract_str.replace("Abstract:", expected + " Abstract:", 1)

    def test_abstract_without_abstract_type_is_extracted(self):
        """
        Test that the first abstract WITHOUT an abstract-type attribute is selected from the JATS XML.
        :return:
        """
        expected = self._jats_with_abstract()
        abstract = self.jats.article_abstract
        assert abstract == expected

    def test_abstract_with_summary_abstract_type_is_extracted(self):
        """
        Test that where several abstracts with different abstract-types are present, the "summary" is extracted.
        :return:
        """
        expected = self._jats_with_abstract(["not-this", "web-summary", "or-this", "summary", "bad"],
                                            remove_original_abstract=True,
                                            expected="SUMMARY")
        abstract = self.jats.article_abstract
        assert abstract == expected

    def test_abstract_with_web_summary_abstract_type_is_extracted(self):
        """
        Test that where several abstracts with different abstract-types are present, the "web-summary" is extracted
        :return:
        """
        expected = self._jats_with_abstract(["not-this", "web-summary", "or-this", "bad"],
                                            remove_original_abstract=True,
                                            expected="WEB-SUMMARY")
        abstract = self.jats.article_abstract
        assert abstract == expected

    def test_abstract_with_unexpected_abstract_type_is_extracted(self):
        """
        Test that the first abstract is extracted, where several abstracts all with different abstract-types are present
        but none of these is one of the 3 possible summary types
        :return:
        """
        expected = self._jats_with_abstract(["this-one", "not-this", "or-this"],
                                            remove_original_abstract=True,
                                            expected="THIS-ONE")
        abstract = self.jats.article_abstract
        assert abstract == expected

    def test_multiple_abstracts(self):
        """
        Test that if there is an abstract with no abstract-type and others with, then the one without an abstract-type
        is extracted.
        :return:
        """
        expected = self._jats_with_abstract(["not-this", "or-this"])
        abstract = self.jats.article_abstract
        assert abstract == expected

    def test_no_abstract(self):
        """
        Test that where no abstract elements exist, None is returned.
        :return:
        """
        self._jats_with_abstract(remove_original_abstract=True)
        abstract = self.jats.article_abstract
        assert abstract is None

    ### Testing LICENCES ###

    def test_multi_license_jats(self):
        jats = JATSFactory.multi_license_xml()
        cc_string = (
            "This article is distributed under the terms of the Creative Commons Attribution License, "
            "which permits unrestricted use and "
            "redistribution provided that the original author and source are credited."
        )
        _, license_details = jats.get_licence_and_article_version_details()
        assert len(license_details) == 1
        license = license_details[0]
        # the url taken from the license_ref should be the one used
        assert "license_ref" in license.get("url")
        assert cc_string in license.get("title")

    def test_no_xlink_multi_license_jats(self):
        factory = JATSFactory
        jats_normal = factory.multi_license_xml()
        jats_no_xlink = factory.multi_license_xml_no_license_xlink()
        assert jats_normal.get_licence_and_article_version_details()[1] == jats_no_xlink.get_licence_and_article_version_details()[1]

    def test_multiple_license_p_jats(self):
        jats = JATSFactory.multi_license_xml_multiple_license_p()
        _, license_details = jats.get_licence_and_article_version_details()
        assert len(license_details) == 1
        assert "fake" in license_details[0].get("title")

    def test_license_p_only(self):
        # tests that when only <license-p> elements are within a <license> that we default to this
        # when there is only url information in an extlink
        jats = JATSFactory.license_p_only_extlink_xml()
        _, license_details = jats.get_licence_and_article_version_details()
        assert len(license_details) == 1
        assert "license_p" in license_details[0].get("url")

        # when there is only url information in the text (no extlinks)
        jats = JATSFactory.license_p_only_no_extlink_xml()
        _, license_details = jats.get_licence_and_article_version_details()
        assert len(license_details) == 1
        assert "license_p" in license_details[0].get("url")

    def test_license_multiple_paragraphs_text(self):
        # test that when there are multiple paragraphs, the title is concatenated together from them
        test_string = "Paragraph 1Paragraph 2"
        jats = JATSFactory.jats_from_file("valid_jats_license_multiple_paragraphs.xml")
        _, license_details = jats.get_licence_and_article_version_details()
        assert len(license_details) == 1
        assert test_string in license_details[0].get("title")

    def test_license_href_no_ali(self):
        # test that when there is an xlink:href in the <license> and no <ali:license_ref> information, that we default
        # to the href value
        jats = JATSFactory.jats_from_file("valid_jats_href_no_ali.xml")
        _, license_details = jats.get_licence_and_article_version_details()
        assert len(license_details) == 1
        assert "href" in license_details[0].get("url")

    def test_license_with_start_date(self):
        jats = JATSFactory.license_with_start_date()
        _, license_details = jats.get_licence_and_article_version_details()
        assert len(license_details) == 1
        assert "2018-09-20" == license_details[0].get("start")

    ### Testing PUBLICATION DATES ###

    def test_pub_date_in_history_date(self):
        jats = JATSFactory.jats_from_file("valid_jats_hindawi.xml")
        _, pub_date = jats.get_history_and_pub_dates()
        assert pub_date == {
            'date': '2016-12-29',
            'year': '2016',
            'month': '12',
            'day': '29',
            'publication_format': 'print'
        }

    def test_duplicate_pub_dates_ok_and_history(self):
        jats = JATSFactory.jats_from_file('valid_jats_duplicate_pub_dates_ok.xml')
        history_list, pub_date = jats.get_history_and_pub_dates()
        assert pub_date == {
            'date': '2016-12-29',
            'year': '2016',
            'month': '12',
            'day': '29',
            'publication_format': 'electronic'
        }

        # Check expected number of history elements have been extracted
        assert len(history_list) == 5

        # Check that returned list matches expected list
        expected_history=[{'date_type': 'received', 'date': '2016-09-15'},
                          {'date_type': 'accepted', 'date': '2016-12-15'},
                          {'date_type': 'epub', 'date': '2016-12-29'},
                          {'date_type': 'ppub', 'date': '2017-01-15'},
                          {'date_type': 'publication-year', 'date': '2016'}
                          ]
        assert (sorted(history_list, key=lambda x: x["date_type"]) ==
                sorted(expected_history, key=lambda x: x["date_type"]))

    def test_hist_dates_error(self):
        jats = JATSFactory.jats_from_file('valid_jats_bad_hist_date.xml')

        with self.assertRaises(InvalidJATSError) as exc:
            _, pub_date = jats.get_history_and_pub_dates()
        assert str(exc.exception) == "Invalid date '2017-02-31' (day is out of range for month) for element: ❮date date-type=\"pub\"❯"

    def test_duplicate_pub_dates_error(self):
        jats = JATSFactory.jats_from_file('valid_jats_duplicate_pub_dates_bad.xml')

        with self.assertRaises(InvalidJATSError) as exc:
            _, pub_date = jats.get_history_and_pub_dates()
        assert str(exc.exception) == 'More that one publication date found for epub type.'

    def test_multiple_pub_dates_ok(self):
        jats = JATSFactory.jats_from_file('valid_jats_multiple_pub_dates_ok.xml')
        hist_dates, pub_date = jats.get_history_and_pub_dates()
        assert pub_date == {
            'date': '2016-11-28',
            'year': '2016',
            'month': '11',
            'day': '28',
            'publication_format': 'electronic'
        }
        assert hist_dates == [
            {'date': '2016', 'date_type': 'publication-year'},
            {'date': '2016-11-28', 'date_type': 'epub'},
            {'date': '2016-09-15', 'date_type': 'received'},
            {'date': '2016-12-15', 'date_type': 'accepted'},
            {'date': '2016-12-29', 'date_type': 'ppub'},
            {'date': '2016-12-29', 'date_type': 'epub-ppub'}
        ]


    ### Testing CONTRIBUTORS ###

    def test_string_name_contributors(self):
        """
        Test that authors and non-authors are correctly extracted from JATS. That (for authors) the corresponding author
        is recognized and that affiliations are captured.
        :return:
        """
        jats = JATSFactory.jats_from_file("valid_jats_string_name_contributors.xml")
        authors = jats.authors
        assert len(authors) == 3
        first = authors[0]
        second = authors[1]
        third = authors[2]
        assert first.get("firstname") == "Chelsea L"
        assert first.get("surname") == "Reighard-in-Name-Alternative"
        assert first.get("type") == "author"
        affs = first.get("affiliations")
        assert len(affs) == 1
        assert affs == [{'raw': 'Affiliation number one'}]
        assert first.get("corresp") is False

        assert second.get("firstname") == "Scott J"
        assert second.get("surname") == "Hollister"
        assert second.get("type") == "an author"
        affs = second.get("affiliations")
        assert len(affs) == 1
        assert [{'raw': 'Affiliation number two'}] == affs

        assert second.get("corresp") is False

        assert third.get("firstname") == "David A"
        assert third.get("surname") == "Zopf"
        assert third.get("type") == "author"
        affs = third.get("affiliations")
        assert len(affs) == 2
        assert [{'raw': 'Affiliation number three'}, {'raw': 'Affiliation number four'}] == affs
        assert third.get("corresp") is True

        contribs = jats.contributors
        assert len(contribs)  == 2
        assert contribs[0].get("surname") == "Editor"
        assert contribs[1].get("surname") == "Translator"


    def test_emails_in_contribs(self):
        # test that when we have multiple <contrib>s pointing to the same set of emails, we only collect
        # if the contributor's surname appears in the email

        jats_xml = JATSFactory.jats_from_file("valid_jats_multiple_xref_corresp.xml")
        authors = jats_xml.authors
        # only kopf should have the email address davidzopf@med.umich.edu associated with him
        # despite the fact that all authors have a <contrib> linked to that address
        for author in authors:
            emails = author.get("emails")
            if emails:
                # Zopf should only have one email
                if author.get("surname") == "Zopf":
                    assert len(emails) == 2
                    assert "davidzopf@med.umich.edu" in emails
                    assert "zopf@email_in_aff.com"  in emails
                    assert "anotherperson@med.umich.edu" not in emails
                else:
                    assert "davidzopf@med.umich.edu" not in emails
        assert len(authors) == 3
        assert len(jats_xml.contributors) == 1

        # test that when we only have one <contrib> pointing to a set of emails, we collect ALL emails regardless
        jats_xml = JATSFactory.jats_from_file("valid_jats_one_xref_corresp.xml")
        authors = jats_xml.authors
        assert len(authors) == 3
        for author in authors:
            emails = author.get("emails")
            if emails:
                # Zopf should have both emails
                if author.get("surname") == "Zopf":
                    assert len(emails) == 2
                    assert "davidzopf@med.umich.edu" in emails
                    assert "anotherperson@med.umich.edu" in emails
        assert len(jats_xml.contributors) == 1

    def test_elocation_id_and_ack(self):
        jats_xml = JATSFactory.jats_from_file("valid_jats_elife.xml")
        assert jats_xml.ack == "Acknowledgements: NS was supported in part by the Stanford Genome Training Program (NIH/NHGRI), JMB by the Biomedical Informatics Training Program (NIH/NLM), and JCB by the Burroughs Wellcome Fund Preterm Birth Initiative. We thank Elizabeth Finn for help with embryo dissections, Ghia Euskirchen and staff of the Stanford Center for Genomics and Personalized Medicine and Ziming Weng for help with sequencing, Cyril Ramathal and the Reijo-Pera lab for qPCR advice, and Casey Brown, Stephen Montgomery, and Eric Stone for discussions and comments on the manuscript. All raw sequencing data are available in the Gene Expression Omnibus ( http://www.ncbi.nlm.nih.gov/geo/) under accession number GSE62967."
        assert jats_xml.page_info_tuple == (None, None, None, "e05538")

    def test_ext_link_in_contrib(self):
        # tests that when we have ext-links in our <contrib> elements, any emails or orcids contained within
        # them are extracted properly
        # for authors
        authors = JATSFactory.jats_from_file("valid_NLM_with_ext_link.xml").authors
        for author in authors:
            # we expect the author Sikora to have successfully had the ext-links of type "email" and "orcid"
            # extracted and placed into the list of emails and id_tuples
            if author.get("surname") == "Sikora":
                assert "email@email.com" in author.get("emails")
                assert ("orcid", "0000-0003-3523-4408") in author.get("id_tuples")

    def test_collab_in_contrib_and_corresp(self):
        # tests that when we have <contrib> element that contains <collab> and no <name> the element text is
        # captured as an organisation_name.  ALSO, test that corresponding authors (those with <contrib corresp="yes">
        # or with an <xref ref-type="corresp">) are properly recognised. AND that <suffix> is captured

        # The XML used by following fixture contains 3 <collab> elements, but one of these exists alongside a <name>
        # element so should be ignored (i.e. not captured as a name)
        # All valid <collab> elements have text starting with "Collab..."
        # Also, one of the authors in the XML (with surname Zopf-Three) is a corresponding author.

        jats_xml = JATSFactory.jats_from_file("valid_jats_collab_contributors.xml")
        authors = jats_xml.authors
        assert len(authors) == 7
        expected_authors = [
           {
              "type": "author",
              "corresp": False,
              "org_name": "Collab one",
              "affiliations": [{"raw": "Medical School, University of Michigan, Ann Arbor, MI, USA"}]
           },
           {
              "type": "author",
              "corresp": False,
              "surname": "Reighard-One",
              "firstname": "Chelsea L",
              "suffix": "",
              "affiliations": [{"raw": "Medical School, University of Michigan, Ann Arbor, MI, USA"}]
           },
           {
              "type": "an author",
              "corresp": False,
              "surname": "Hollister-Two-in-Name-Alternatives",
              "firstname": "Scott J",
              "suffix":"",
              "affiliations": [{"raw": "Department of Biomedical Engineering, Georgia Institute of Technology, Atlanta, GA, USA"}]
           },
           {
              "type": "author",
              "corresp": True,
              "surname": "Zopf-Three",
              "firstname": "David A",
              "suffix": "Snr.",
              "emails": ["davidzopf-three@med.umich.edu"],
              "affiliations": [
                 {"raw": "Otolaryngology – Head & Neck Surgery, Pediatric Division, University of Michigan Health Systems, CS Mott Children's Hospital, Ann Arbor, MI, USA"},
                 {"raw": "Department of Biomedical Engineering, University of Michigan, Ann Arbor, MI, USA"}
              ]
           },
           {
              "type": "author",
              "corresp": True,
              "surname": "Corresponder",
              "firstname": "Second corresp author",
              "suffix": "",
              "emails": ["corresponder@med.umich.edu"],
              "affiliations": [{"raw": "A locally defined affiliation."}]
           },
           {
              "type": "author",
              "corresp": False,
              "org_name": "Collab two",
              "affiliations": [{"raw": "A locally defined affiliation."}]
           },
           {
              "type": "author",
              "corresp": False,
              "surname": "Name-With-Collab",
              "firstname": "Collab Should Not Be Captured",
              "suffix": "",
              "affiliations": [{"raw": "Another locally defined affiliation."}]
           }
        ]
        assert authors == expected_authors

        contribs = jats_xml.contributors
        assert len(contribs) == 1
        assert contribs[0].get("surname") == "Editor"
        assert contribs[0].get("affiliations")[0] == {"raw": "A locally defined Editor affiliation."}

    def test_collab_name_and_collab_wrap_jats_v1_4(self):
        """
        Test the following:
            The new <collab-name> element should be used in addition to the existing <collab> element to populate organisation_name.

            Use of <collab-wrap> element which allows for members of a collaboration to be identified, together with their affiliations within nested <contrib> elements (within <contrib-group>):

            <contrib-group>
              <contrib>
                 <collab-wrap collab-type="research group">
                   <collab-name>…</collab-name>
                   <contrib-group>
                      <contrib>…</contrib>
                      <contrib>…</contrib>
                      <contrib>…</contrib>
                   </contrib-group>
                </collab-wrap>
              </contrib>
        :return:
        """
        jats_xml = JATSFactory.jats_from_file("valid_jats_collab-name_collab-wrap.xml")
        authors = jats_xml.authors
        assert len(authors) == 7
        expected_authors = [
           {
              "type": "author",
              "corresp": False,
              "org_name": "Collab ONE (no alternative)",
              "affiliations": [{"raw": "Medical School, University of Michigan, Ann Arbor, MI, USA"}]
           },
           {
              "type": "author",
              "corresp": False,
              "org_name": "Collab TWO (English alternative)",
              "affiliations": [{"raw": "Medical School, University of Michigan, Ann Arbor, MI, USA"}]
           },
           {
              "type": "author",
              "corresp": False,
              "surname": "Bausenbach",
              "firstname": "Ardie",
              "suffix": "[Collab THREE (Research Group with Members)]",
              "affiliations": [{"org": "Collab group Institution (Bausenbach)"}]
           },
           {
              "type": "author",
              "corresp": False,
              "surname": "Beck",
              "firstname": "Jeffrey",
              "suffix": "[Collab THREE (Research Group with Members)]",
              "affiliations": [{"raw": "Nested Xref Contrib Group Affiliation FIVE"}]
           },
           {
              "type": "author",
              "corresp": False,
              "surname": "Group-Author",
              "firstname": "Isa",
              "suffix": "Snr. [Collab THREE (Research Group with Members)]",
              "affiliations": [
                 {"org": "Collab group Institution (Group-Author)"},
                 {"raw": "Nested Xref Contrib Group Affiliation SIX"}
              ]
           },
           {
              "type": "author",
              "corresp": False,
              "org_name": "Collab THREE (Research Group with Members)"
           },
            {
                "type": "author",
                "corresp": True,
                "surname": "Zopf-Three",
                "firstname": "David A",
                "suffix": "Snr.",
                "emails": ["corresponder@med.umich.edu"],
                "affiliations": [
                    {"raw": "Otolaryngology – Head & Neck Surgery, Pediatric Division, University of Michigan Health Systems, CS Mott Children's Hospital, Ann Arbor, MI, USA"}
                ]
            }
        ]
        assert authors == expected_authors

        contribs = jats_xml.contributors
        assert len(contribs) == 1
        assert contribs[0].get("surname") == "Editor"
        assert contribs[0].get("affiliations")[0] == {"raw": "A locally defined Editor affiliation."}

    ### Testing FUNDERS ###

    def test_named_content_funder_id(self):
        # tests that when we have funder ids in named content with content-type funder-id,
        # they're captured as funder ids
        funding = JATSFactory.jats_from_file("valid_NLM_content_type_funder_id.xml").grant_funding
        test_case_found = False
        for funder in funding:
            if funder.get("name") == "Austrian Science Fund":
                test_case_found = True
                id = funder.get("identifier")
                assert len(id) == 1
                assert id[0].get("id") == "example_id"
        assert test_case_found

    def test_named_content_name(self):
        # tests that when we have a name in named content with content-type including name, they're captured
        # as funder names
        funding = JATSFactory.jats_from_file("valid_NLM_content_type_name.xml").grant_funding
        test_case_found = False
        for funder in funding:
            name = funder.get("name")
            if "Austrian Science Fund" in name:
                test_case_found = True
                assert "example_name" in name
        assert test_case_found

    def test_named_content_neither(self):
        # tests that when we have something in named content with a content-type neither name or funder-id
        # then nothing is captured from it
        funding = JATSFactory.jats_from_file("valid_NLM_content_type_neither.xml").grant_funding
        test_case_found = False
        for funder in funding:
            if funder.get("name") == "Austrian Science Fund":
                test_case_found = True
                assert not funder.get("identifier")
                assert funder.get("grant_numbers") == ['P 29130-G27']
        assert test_case_found

    ### Affiliation ###

    def test_no_id_affiliations(self):
        jats = JATSFactory.jats_from_file("valid_jats_aff_no_id.xml")
        authors = jats.authors
        assert authors
        author = authors[0]
        assert author.get("affiliations") == [
            {'street': 'Warsaw',
             'org': 'Nicolaus Copernicus Astronomical Center, Polish Academy of Sciences',
             'country': 'Poland',
             'raw': 'Nicolaus Copernicus Astronomical Center, Polish Academy of Sciences, Warsaw, Poland'}
        ]

    def test_affilations_permutations(self):
        """
        Expect 13 authors to have varying affiliations & emails.
        """
        jats = JATSFactory.jats_from_file("valid_jats_affiliation_variations.xml")

        expected_affs = [
            [{'raw': 'Xref affiliation #1'}],   # Author 1

            [{'org': 'Xref aff-alternative #2'}],   # Author 2

            [{'raw': 'Local Aff-A locally defined affiliation.'},
             {'org': 'Xref aff-alternative #2'}],   # Author 3

            [{'org': 'Local Aff-B',
              'postcode': 'TW11 0LW',
              'country': 'United Kingdom',
              'country_code': 'GB',
              'raw': 'Local Aff-B locally defined affiliation. United Kingdom TW11 0LW'}],   # Author 4

            [{'raw': 'Xref affiliation #4'},
             {'raw': 'External Xref affiliation #5'}],   # Author 5

            [{'identifier': [
                {'type': 'GRID', 'id': 'grid.aff.c'},
                {'type': 'ROR', 'id': 'https://ror.org/aff-c'}],
              'street': '33 Hampton Road, Somewhere',
              'org': 'Local Aff-C locally defined affiliation',
              'dept': "Dean's Office, Chemistry Dept",
              'city': 'Teddington',
              'state': 'Greater London',
              'postcode': 'TW11 0LW',
              'country': 'United Kingdom',
              'country_code': 'GB',
              'raw': "START Local Aff-C locally defined affiliation, Dean's Office, Chemistry Dept, 33 Hampton Road, Somewhere, Teddington, Greater London, Random element, YYY, United Kingdom, ZZZ bold element, TW11 0LW, The Universe (GRID: grid.aff.c, ROR: https://ror.org/aff-c)"}],

            [],   # Author 7

            [{'identifier': [
                {'type': 'GRID', 'id': 'grid.aff.e'},
                {'type': 'ROR', 'id': 'https://ror.org/aff-e'}],
              'street': '33e Hampton Road',
              'org': 'Local Aff-E locally defined affiliation',
              'dept': "Chemistry Dept",
              'city': 'Teddington',
              'state': 'Greater London',
              'postcode': 'TW11 0LW',
              'country': 'England',
              'raw': "START Local Aff-E locally defined affiliation, Chemistry Dept, 33e Hampton Road, Teddington, Greater London, England, TW11 0LW, (GRID: grid.aff.e, ROR: https://ror.org/aff-e)"}],   # Author 8

            [{'raw': 'Group affiliation #9'},
             {'org': 'Group aff-alternative #10'},
             {'raw': 'External Xref affiliation #5'}],   # Author 9

            [{'raw': 'Group affiliation #9'},
             {'org': 'Group aff-alternative #10'},
             {'raw': 'Local Aff-D locally defined affiliation.'},
             {'org': 'External Xref aff-alternative #6'},
             {'identifier': [
                {'type': 'GRID', 'id': 'grid.exaff7'}],
              'dept': 'Department of EXAFF7',
              'org': 'University of BOLD ITALIC EXAFF7',
              'city': 'Bristol',
              'raw': 'Prefix text X Department of EXAFF7 ITALIC XYZ, University of BOLD ITALIC EXAFF7, Bristol, BS2 9XX, UK LAST (GRID: grid.exaff7)'}],   # Author 10
            [{'raw': 'Group affiliation #9'},
             {'org': 'Group aff-alternative #10'}],  # Author 11

            [{'raw': 'Contrib Group 4 affiliation #1'}, {'raw': 'Contrib Group 4 affiliation #2'}],  # Author 12

            [{'raw': 'Contrib Group 4 affiliation #1'}, {'raw': 'Contrib Group 4 affiliation #2'}]  # Author 13
        ]
        expected_emails = [
            [],     # Author 1
            [],     # Author 2
            [],     # Author 3
            ['author4@email.com'],     # Author 4
            ['aff4@email.com', 'exaff5-one@email.com', 'exaff5-two@email.com'],     # Author 5
            [],     # Author 6
            [],     # Author 7
            [],     # Author 8
            ['exaff5-one@email.com', 'exaff5-two@email.com'],     # Author 9
            [],     # Author 10
            [],     # Author 11
            ["aff4.1@email.com"],     # Author 12
            ["aff4.1@email.com"]      # Author 13
        ]
        for ix, auth in enumerate(jats.authors):
            affs = auth.get("affiliations", [])
            # print(ix, "\n", affs, "\n", expected_affs[ix])
            assert affs == expected_affs[ix]

            emails = auth.get("emails", [])
            # print(ix, emails, expected_emails[ix])
            assert sorted(emails) == sorted(expected_emails[ix])


#     def test_manual_investigation(self):
#       """
#           Uncomment for manual testing of process.
#       """
#         j = JATS(raw="""<?xml version="1.0"?>
# <!DOCTYPE article PUBLIC "-//NLM//DTD JATS (Z39.96) Journal Archiving and Interchange DTD with OASIS Tables with MathML3 v1.1 20151215//EN" "JATS-archive-oasis-article1-mathml3.dtd">
# <article article-type="review-article" xmlns:xlink="http://www.w3.org/1999/xlink">
# 	<front>
# <article-meta>
# 			<contrib-group>
# 				<contrib contrib-type="author">
# 					<collab>Collab one (contrib group 1, Author-1): XAff-1</collab>
# 					<xref ref-type="aff" rid="AFF1"><sup>1</sup></xref>
# 				</contrib>
#
#             <aff id="AFF1">
# 				<label>
# 					<sup>53</sup>
# 				</label>
# 				Department of Knees
# 				<institution>Health and Medical University</institution>
# 				Office of <bold>quacks</bold>
# 				<city>Potsdam</city>
# 				<country country="DE">Germany</country>
# 			</aff>
# 			</contrib-group>
# 			</article-meta>
# 			</front>
# 			</article>
#         """)
#         a = j.authors
#         print(a[0]["affiliations"][0].get("raw", ""))
