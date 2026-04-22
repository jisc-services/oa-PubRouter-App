# Unit tests related to  JATS article specific use and selection of appropriate licences

# NOTE on spelling:  "licence" and "licences" are UK English, but JATS NLM uses USA English "license", hence
# <ali:license_ref> and <license> elements - which is reflected by differing spellings of variable names.

from lxml import etree
from unittest import TestCase
from router.jper.models.jats import InvalidJATSError
from tests.jper_tests.fixtures.models import JATSFactory

class TestSpecificUse(TestCase):
    # any licence will do
    BASE_LICENCE = "http://creativecommons.org/licenses/by/4.0/"

    def _set_jats(self, article_specific_use, lic_urls_n_specific_uses=None, spec_use_in_lic_ref=True):
        """
        Sets self.jats to have specified values
        :param article_specific_use: specific-use value to set for article
        :param lic_urls_n_specific_uses: list of (lic-url, specific-use) tuples we wish to set licences for
        :param spec_use_in_lic_ref: whether specific-use of licences should be added as attribute in <license> 
            or <ali:license_ref> elements 
        :return: 
        """
        # initial jats
        self.jats = JATSFactory.jats_from_file("valid_jats_specific_use_base.xml")
        if lic_urls_n_specific_uses:
            # add licences
            self._set_jats_licences(lic_urls_n_specific_uses, spec_use_in_lic_ref)

        # change article's specific-use attribute
        self._set_jats_article_specific_use(article_specific_use)

    def _set_jats_article_specific_use(self, article_version):
        """
        Set 'specific-use' attribute on JATS <article> element. E.g. <article specific-use="VoR">.
        :param article_version: String - article version (e.g. "VoR")
        :return: Nothing
        """
        # sets the article's specific-use attribute - if None, doesn't set it at all
        if article_version is not None:
            self.jats.xml.set("specific-use", article_version)

    def _set_jats_article_versions(self, article_versions, vocab=None, delete_first=True):
        """
        Create <article-version> element containing article version (like 'VoR') under <article-meta>, OR create
        1 or more <article-version> elements grouped within an <article-version-alternatives> element under <article-meta>.

        The article-version value stored as the element text if vocab is None otherwise as the article-version-type
        attribute.

        IMPORTANT: If multiple article_versions are specified AND vocab is NOT None, then only the first element
        will have the vocab attribute set, but article-version-type is still set for all entries.

        :param article_versions: String - article version (e.g. "VoR") or List of Strings ["VoR", "P"]
        :param vocab: String - vocabulary to use ("JAV" or "NISO-RP-8-2008") or None
        :param delete_first: Boolean - True: Remove any pre-existing <article-version> elements
        :return: Nothing
        """
        if delete_first:
            existing_list = self.jats.xml_article_meta.xpath("./article-version|./article-version-alternatives")
            if existing_list:
                # We only ever expect a single element
                self.jats.xml_article_meta.remove(existing_list[0])

        # sets the article's specific-use attribute - if None, doesn't set it at all
        if article_versions is not None:
            if isinstance(article_versions, list):
                art_ver_root = etree.Element("article-version-alternatives")
                self.jats.xml_article_meta.append(art_ver_root)
            else:
                # We have a single string, convert it to a list
                article_versions = [article_versions]
                art_ver_root = self.jats.xml_article_meta

            attr = None
            for art_ver in article_versions:
                if vocab:
                    # Only set the vocab attribute for the first article-version
                    if attr is None:
                        attr = {"vocab": vocab, "article-version-type": art_ver}
                    else:
                        attr = {"article-version-type": art_ver}
                art_ver_el = etree.Element("article-version", attrib=attr)
                if vocab is None:
                    art_ver_el.text = art_ver
                art_ver_root.append(art_ver_el)
        # print(etree.tostring(self.jats.xml, encoding="unicode", pretty_print=True))

    def _set_jats_licences(self, lic_urls_n_specific_uses, spec_use_in_lic_ref):
        """
        For each tuple in a list of licence-urls-&-specific-use-values, the function adds a <license> element with
        a <license_ref> element inside. The licence URL and specific-use attribute are determined by the tuple contents.
        
        The specific-use attribute gets placed in either the <license> element or <ali:license_ref> element, depending
        on the value of `spec_use_in_lic_ref`: True --> <ali:license_ref> element; False --> <license> element.
        
        If a specific-use value in the tuple is None, then the licence has NO specific-use attribute set. 

        :param lic_urls_n_specific_uses: list of (lic-url, specific-use) tuples we wish to set licences for
        :param spec_use_in_lic_ref: Boolean - True: specific-use appears in license or license_ref; False: does not appear
        """
        permissions = self.jats.xml_article_meta.find("./permissions")
        for url, specific_use in lic_urls_n_specific_uses:
            # make a <license>
            license = etree.Element("license")
            # make an <ali:license_ref> and add the base license to it's text
            license_ref = etree.Element("{http://www.niso.org/schemas/ali/1.0/}license_ref")
            license_ref.text = url
            if specific_use is not None:
                # set the specific-use attribute in either the <ali:license_ref> element or the <license> element
                # depending on value of spec_use_in_lic_ref
                if spec_use_in_lic_ref:
                    license_ref.set("specific-use", specific_use)
                else:
                    license.set("specific-use", specific_use)
            # add the <ali:license_ref> as a sub element of the <license> element
            license.append(license_ref)
            # add the <license> element to the <permissions> element
            permissions.append(license)


    def test_no_licences(self):
        """
        Confirm that if there are no licences, but there is a valid article specific-use then that is used
        """
        # Create JATS object with no licences
        self._set_jats(None, lic_urls_n_specific_uses=[])
        for set_specific_use, expected_art_vers in (
            # (Specific-use value to set, Expected_article_version returned)
            ("VoR", "VOR"),
            ("vor", "VOR"),
            ("EVoR", "EVOR"),
            ("cvor", "CVOR"),
            ("C/EVoR", "C/EVOR"),
            ("AM", "AM"),
            ("p", "P"),
            # The following are invalid Article specific-user values
            ("AO", None),
            ("BAD", None),
            ("", None),
            (None, None)
        ):
            # Set JATS <article> element's specific-use attribute
            self._set_jats_article_specific_use(set_specific_use)
            article_version, licences = self.jats.get_licence_and_article_version_details()
            assert expected_art_vers == article_version
            assert licences == []


    def test_valid_article_no_licences_with_specific_use(self):
        """
        Check that where none of the licences has a specific use, then a valid article specific-use is taken from
        <article> element and ALL licences are returned.
        """
        # Create JATS object with 3 licences, none with specific use
        self._set_jats(None, lic_urls_n_specific_uses=[
            (self.BASE_LICENCE + "1", None),
            (self.BASE_LICENCE + "2", None),
            (self.BASE_LICENCE + "3", None),
        ])
        for set_specific_use, expected_art_vers in (
            # (Specific-use value to set, Expected_article_version returned)
            ("VoR", "VOR"),
            ("EVoR", "EVOR"),
            ("cvor", "CVOR"),
            ("C/EVoR", "C/EVOR"),
            ("AM", "AM"),
            ("aam", "AM"),      # AAM should be treated as "AM"
            ("p", "P"),
            # The following are invalid Article specific-user values
            ("BAD", None),
            ("", None),
            (None, None)
        ):
            # Set JATS <article> element's specific-use attribute
            self._set_jats_article_specific_use(set_specific_use)
            article_version, licences = self.jats.get_licence_and_article_version_details()
            assert expected_art_vers == article_version
            # Expect all 3 licences to be returned in each case
            assert len(licences) == 3


    def test_valid_article_some_invalid_licences(self):
        """
        Check that if any licences has invalid article-version that an ERROR is raised
        """
        set_expected_art_vers = [
            # (Specific-use value to set, Expected_article_version returned)
            ("VoR", "VOR"),
            ("AM", "AM"),
            # The following are invalid Article specific-user values
            ("BAD", None),
            (None, None)
        ]
        lic_urls_n_specific_uses = [
            (self.BASE_LICENCE + "1", "BAD"),   # Bad specific-use
            (self.BASE_LICENCE + "2", "VoR"),   # OK specific-use
            (self.BASE_LICENCE + "3", None),    # OK (no specific-use)
        ]
        # Run test twice, first with licence specific use set in the ali:license_ref element, and again with it set elsewhere
        for specific_use_in_license_ref in (True, False):
            # Create JATS object with 3 licences, 1 having an INVALID specific-use - with the Licence specific-use values
            # either in the <ali:license_ref> element OR in the enclosing <license> element
            self._set_jats(None,
                           lic_urls_n_specific_uses=lic_urls_n_specific_uses,   # 3 licences, 1 with a bad specific-use
                           spec_use_in_lic_ref=specific_use_in_license_ref  # True or False
                           )
            for set_specific_use, expected_art_vers in set_expected_art_vers:
                # Set JATS <article> element's specific-use attribute
                self._set_jats_article_specific_use(set_specific_use)
                with self.assertRaises(InvalidJATSError) as exc:
                    article_version, licences = self.jats.get_licence_and_article_version_details()
                assert "Found a licence with invalid specific-use value: 'BAD'" in str(exc.exception)


    def test_valid_article_different_licence_specific_uses(self):
        """
        When there is a valid article-type, and multiple licences with a mixture of different specific-use values
        """
        # 2 of the licences have specific-use of equivalent to "AM" ("AAM" and "AM")
        lic_urls_n_specific_uses = [
            (self.BASE_LICENCE + "P", "P"),
            (self.BASE_LICENCE + "AM_1", "am"),
            (self.BASE_LICENCE + "AM_2", "aam"),
            (self.BASE_LICENCE + "TDM", "tdm")
        ]
        ## 1 ## - Article-version ("AM") matches some of the licences specific-use values
        # Run test twice, first with licence specific use set in the ali:license_ref element, and again with it set elsewhere
        for specific_use_in_license_ref in (True, False):
            # Create JATS object with 4 licences, All with valid specific-use
            # either in the <ali:license_ref> element OR in the enclosing <license> element
            # 2 of licences have specific-use matching the article specific-use (AM)
            self._set_jats("AM",
                           lic_urls_n_specific_uses=lic_urls_n_specific_uses,   # 4 licences
                           spec_use_in_lic_ref=specific_use_in_license_ref  # True or False
                           )
            article_version, licences = self.jats.get_licence_and_article_version_details()
            assert article_version == "AM"
            # Both licences with specific-use of VoR should have been captured
            assert 2 == len(licences)
            for x, lic in enumerate(licences, start=1):
                assert lic["url"].endswith(f"AM_{x}")
                assert "AM" == lic["specific-use"]

        ## 2 ## - Article-version ("VoR") DOES NOT match any of the licences specific-use value
        for specific_use_in_license_ref in (True, False):
            # Create JATS object with 4 licences, All with valid specific-use
            # either in the <ali:license_ref> element OR in the enclosing <license> element - but NONE has a specific-use
            # that matches the article specific-use (VoR)
            self._set_jats("VoR",
                           lic_urls_n_specific_uses=lic_urls_n_specific_uses,   # 4 licences
                           spec_use_in_lic_ref=specific_use_in_license_ref  # True or False
                           )
            with self.assertRaises(InvalidJATSError) as exc:
                article_version, licences = self.jats.get_licence_and_article_version_details()
            assert "Valid article version value 'VOR', but no licences share this in their specific-use attribute" in str(exc.exception)


    def test_invalid_article_no_licences_with_specific_use(self):
        """
        Where there is an invalid or no article-version, & no licences have a specific-use then expect ALL licences
        to be returned, with NO article-version value
        """
        # 3 licences, none has a specific-use
        lic_urls_n_specific_uses = [
            (self.BASE_LICENCE + "1", None),
            (self.BASE_LICENCE + "2", None),
            (self.BASE_LICENCE + "3", None),
        ]
        # Create JATS object with 3 licences, none with specific use
        self._set_jats(None, lic_urls_n_specific_uses=lic_urls_n_specific_uses)

        # for bad or no article-specific usevalues
        for set_specific_use in ("tdm", "BAD", None):
            # Set JATS <article> element's specific-use attribute
            self._set_jats_article_specific_use(set_specific_use)

            article_version, licences = self.jats.get_licence_and_article_version_details()
            assert article_version is None
            assert len(licences) == 3


    def test_invalid_article_some_invalid_licences(self):
        """
        Where there is an invalid or no article-version, with multiple licences, at least 1 of which has INVALID
        specific-use, then expect ERROR to be raised
        """
        # 3 licences, none has a specific-use
        lic_urls_n_specific_uses = [
            (self.BASE_LICENCE + "NONE", None),
            (self.BASE_LICENCE + "BAD", "BAD"),
            (self.BASE_LICENCE + "VOR", "VoR"),
        ]
        # Create JATS object with 3 licences, one of which has a BAD specific-use
        self._set_jats(None, lic_urls_n_specific_uses=lic_urls_n_specific_uses)

        # for bad or no article-specific usevalues
        for set_specific_use in ("tdm", "BAD", None):
            # Set JATS <article> element's specific-use attribute
            self._set_jats_article_specific_use(set_specific_use)

            with self.assertRaises(InvalidJATSError) as exc:
                article_version, licences = self.jats.get_licence_and_article_version_details()
            assert "Found a licence with invalid specific-use value: 'BAD'" in str(exc.exception)


    def test_invalid_article_consistent_valid_licences(self):
        """
        Where there is an invalid or no article-version, with multiple licences ALL with same
        specific-use, then expect article-version to be set to the common licence specific-use value, and all
        licences to be captured.
        """
        # 5 licences, have same specific-use values (case insensitive)
        lic_urls_n_specific_uses = [
            (self.BASE_LICENCE + "1", "VOR"),
            (self.BASE_LICENCE + "2", "vor"),
            (self.BASE_LICENCE + "3", "VoR"),
            (self.BASE_LICENCE + "4", "version-of-record"),
            (self.BASE_LICENCE + "5", "Version of Record")
        ]
        # Create JATS object with 5 licences
        self._set_jats(None, lic_urls_n_specific_uses=lic_urls_n_specific_uses)

        # for bad or no article-specific-use values
        for set_specific_use in ("tdm", "BAD", None):
            # Set JATS <article> element's specific-use attribute
            self._set_jats_article_specific_use(set_specific_use)

            article_version, licences = self.jats.get_licence_and_article_version_details()
            assert "VOR" == article_version
            assert 5 == len(licences)


        ### Repeat this time with "AM" or "AAM" licences which are both treated as "AM"  ###
        # 3 licences, have same specific-use values (case insensitive)
        lic_urls_n_specific_uses = [
            (self.BASE_LICENCE + "1", "AM"),
            (self.BASE_LICENCE + "2", "AAM"),
            (self.BASE_LICENCE + "3", "aam"),
        ]
        # Create JATS object with 3 licences
        self._set_jats(None, lic_urls_n_specific_uses=lic_urls_n_specific_uses)

        # for bad or no article-specific usevalues
        for set_specific_use in ("tdm", "BAD", None):
            # Set JATS <article> element's specific-use attribute
            self._set_jats_article_specific_use(set_specific_use)

            article_version, licences = self.jats.get_licence_and_article_version_details()
            assert "AM" == article_version
            assert 3 == len(licences)


    def test_invalid_article_different_valid_specific_use_licences(self):
        """
        No valid article-version, with multiple licences with differing specific-uses --> should raise ERROR.
        """
        # 3 licences, have same specific-use values (case insensitive)
        lic_urls_n_specific_uses = [
            (self.BASE_LICENCE + "VOR", "VoR"),
            (self.BASE_LICENCE + "TDM", "tdm"),
            (self.BASE_LICENCE + "AM", "am"),
        ]
        # Create JATS object with 3 licences
        self._set_jats(None, lic_urls_n_specific_uses=lic_urls_n_specific_uses)

        # for bad or no article-specific usevalues
        for set_specific_use in ("tdm", "BAD", None):
            # Set JATS <article> element's specific-use attribute
            self._set_jats_article_specific_use(set_specific_use)

            with self.assertRaises(InvalidJATSError) as exc:
                article_version, licences = self.jats.get_licence_and_article_version_details()
            assert "No valid article version value and licenses have contrasting specific-use values"\
                   in str(exc.exception)


    def test_covid_19_tdm_specific_use(self):
        """
        Confirm that 'covid-19-tdm' is equivalent to 'tdm' specific-use license, which is IGNORED
        # Pivotal: #173489077
        """
        set_expected_art_vers = [
            # (Specific-use value to set, Expected_article_version returned)
            ("VoR", "VOR"),
            ("AM", "AM"),
            # The following are invalid Article specific-user values
            ("tdm", None),
            ("BAD", None),
            (None, None)
        ]
        lic_urls_n_specific_uses = [
            (self.BASE_LICENCE + "1", "covid-19-tdm"),
            (self.BASE_LICENCE + "2", "COVID-TDM-20"),
            (self.BASE_LICENCE + "3", "TDM"),
            (self.BASE_LICENCE + "4", "tdm"),
        ]
        # Run test twice, first with licence specific use set in the ali:license_ref element, and again with it set elsewhere
        for specific_use_in_license_ref in (True, False):
            # Create JATS object with 4 tdm licences
            # either in the <ali:license_ref> element OR in the enclosing <license> element
            self._set_jats(None,
                           lic_urls_n_specific_uses=lic_urls_n_specific_uses,   # 4 tdm licences
                           spec_use_in_lic_ref=specific_use_in_license_ref  # True or False
                           )
            for set_specific_use, expected_art_vers in set_expected_art_vers:
                # Set JATS <article> element's specific-use attribute
                self._set_jats_article_specific_use(set_specific_use)

                article_version, licences = self.jats.get_licence_and_article_version_details()
                assert expected_art_vers == article_version
                assert licences == []   # NO licences expected

        # Now set article-version to AM and add an AM licence to the list of licences: 4 tdm licences + 1 AM licence
        # This AM licence should be captured
        lic_urls_n_specific_uses.append((self.BASE_LICENCE + "AM_5", "am"))
        self._set_jats("AM",
                       lic_urls_n_specific_uses=lic_urls_n_specific_uses,
                       spec_use_in_lic_ref=True
                       )
        article_version, licences = self.jats.get_licence_and_article_version_details()
        assert "AM" == article_version
        assert 1 == len(licences)
        assert licences[0]["url"].endswith("AM_5")


    def test_jats_article_version_element(self):
        """
        Confirm that article version values can be extracted from <article-version> element which was introduced in
        JATS v1.2.
        """
        art_vers_set_expected = [
            # (short-form-article-version to set, long-form-article-version to set,  Expected_article_version returned)
            ("VoR", "version-of-record", "VOR"),
            ("vor", "version of record", "VOR"),
            ("EVoR", "enhanced-version-of-record", "EVOR"),
            ("cvor", "corrected-version-of-record", "CVOR"),
            ("C/EVoR", "Corrected or Enhanced Version of Record", "C/EVOR"),
            ("AM", "accepted-manuscript", "AM"),
            ("p", "proof", "P"),
            # THis is unacceptable article-version value
            ("AO", "authors original", None),
            # The following are invalid NISO article-version values
            ("BAD", "bad", False),
            ("", "", False)
        ]
        # Create JATS object with no licences or <article-version> element(s)
        self._set_jats(None, lic_urls_n_specific_uses=[])

        # Test single article-version
        for short_art_ver, long_art_ver, expected_art_vers in art_vers_set_expected:
            # Where vocab is NOT being set, then the expected article version will be None instead of False
            false_to_none_expected_art_vers = expected_art_vers or None
            # 1 - Confirm short-form article-version extracted from within <article-version>XXX</article-version> element
            # e.g. <article-version>C/EVoR</article-version>
            self._set_jats_article_versions(short_art_ver)
            article_version, licences = self.jats.get_licence_and_article_version_details()
            assert false_to_none_expected_art_vers == article_version

            # 2 - Confirm long-form article-version extracted from within <article-version>XXX</article-version> element
            # e.g. <article-version>accepted manuscript</article-version>
            self._set_jats_article_versions(long_art_ver)
            article_version, licences = self.jats.get_licence_and_article_version_details()
            assert false_to_none_expected_art_vers == article_version

            # 3 - Confirm short-form article-version extracted from within <article-version article-version-type="XXX"> attribute
            # e.g.: <article-version article-version-type="VoR" vocab="JAV">
            self._set_jats_article_versions(short_art_ver, vocab="JAV")
            if expected_art_vers is False:
                with self.assertRaises(InvalidJATSError) as exc:
                    article_version, licences = self.jats.get_licence_and_article_version_details()
                assert f"Invalid JAV article-version-type: '{short_art_ver}'" in str(exc.exception)
            else:
                article_version, licences = self.jats.get_licence_and_article_version_details()
                assert expected_art_vers == article_version


            # 4 - Confirm long-form article-version extracted from within <article-version article-version-type="XXX"> attribute
            # e.g.: <article-version article-version-type="accepted manuscript" vocab="NISO-RP-8-2008">
            self._set_jats_article_versions(long_art_ver, vocab="NISO-RP-8-2008")
            if expected_art_vers is False:
                with self.assertRaises(InvalidJATSError) as exc:
                    article_version, licences = self.jats.get_licence_and_article_version_details()
                assert f"Invalid NISO-RP-8-2008 article-version-type: '{long_art_ver}'" in str(exc.exception)
            else:
                article_version, licences = self.jats.get_licence_and_article_version_details()
                assert expected_art_vers == article_version


        ##
        ### Test multiple article-version instances which are grouped within an <article-version-alternatives> element ###
        ### Vocab NOT set
        ##
        art_vers_set_expected = [
            # ([short-form-article-version to set], [long-form-article-version to set],  Expected_article_version returned)
            (["dummy", "VoR"], ["a dummy", "version-of-record"], "VOR"),
            (["one", "two", "am", "four"], ["one one", "two two", "accepted manuscript", "four four"], "AM"),
            (["EVoR"], ["enhanced-version-of-record"], "EVOR"),
            # The following are invalid NISO article-version values
            (["one", "two", "three"], ["one one", "two two", "three three"], None),
        ]

        # Create JATS object with no licences or <article-version> element(s)
        self._set_jats(None, lic_urls_n_specific_uses=[])

        # Test different scenarios of multiple <article-version> nested within <article-version-alternatives>
        for short_art_ver, long_art_ver, expected_art_vers in art_vers_set_expected:
            # 1 - Confirm short-form article-version is extracted from <article-version> element text
            # <article-version-alternatives><article-version>XXX</article-version>...</article-version-alternatives>
            # e.g. <article-version>C/EVoR</article-version>
            self._set_jats_article_versions(short_art_ver)
            article_version, licences = self.jats.get_licence_and_article_version_details()
            assert expected_art_vers == article_version

            # 2 - Confirm long-form article-version is extracted from <article-version> element text
            # <article-version-alternatives><article-version>XXX</article-version>..</article-version-alternatives> element
            # e.g. <article-version>accepted manuscript</article-version>
            self._set_jats_article_versions(long_art_ver)
            article_version, licences = self.jats.get_licence_and_article_version_details()
            assert expected_art_vers == article_version


        ##
        ### Test multiple article-version instances which are grouped within an <article-version-alternatives> element ###
        ### Vocab IS set
        ##
        art_vers_set_expected = [
            # ([short-form-article-version to set], [long-form-article-version to set],  Expected_article_version returned)
            (["VoR", "dummy"], ["version-of-record", "a dummy"], "VOR"),
            (["am", "one", "two", ], ["accepted manuscript", "one one", "two two"], "AM"),
            (["EVoR"], ["enhanced-version-of-record"], "EVOR"),
            # The following are invalid NISO article-version values
            (["one", "two", "three"], ["one one", "two two", "three three"], None),
        ]

        # Create JATS object with no licences or <article-version> element(s)
        self._set_jats(None, lic_urls_n_specific_uses=[])

        # Test different scenarios of multiple <article-version> nested within <article-version-alternatives>
        for short_art_ver, long_art_ver, expected_art_vers in art_vers_set_expected:
            # 1 - Confirm short-form article-version is extracted from article-version-type attribute
            # <article-version-alternatives><article-version article-version-type="XXX">...</article-version-alternatives>
            # e.g.: <article-version-alternatives><article-version article-version-type="VoR" vocab="JAV">...
            self._set_jats_article_versions(short_art_ver, vocab="JAV")
            if expected_art_vers is None:
                with self.assertRaises(InvalidJATSError) as exc:
                    article_version, licences = self.jats.get_licence_and_article_version_details()
                assert f"Invalid JAV article-version-type: '{short_art_ver[0]}'" in str(exc.exception)
            else:
                article_version, licences = self.jats.get_licence_and_article_version_details()
                assert expected_art_vers == article_version

            # 2 - Confirm long-form article-version is extracted from article-version-type attribute
            # <article-version-alternatives><article-version article-version-type="XXX">...</article-version-alternatives>
            # e.g.: <article-version-alternatives><article-version article-version-type="accepted manuscript" vocab="NISO-RP-8-2008">...
            self._set_jats_article_versions(long_art_ver, vocab="NISO-RP-8-2008")
            if expected_art_vers is None:
                with self.assertRaises(InvalidJATSError) as exc:
                    article_version, licences = self.jats.get_licence_and_article_version_details()
                assert f"Invalid NISO-RP-8-2008 article-version-type: '{long_art_ver[0]}'" in str(exc.exception)
            else:
                article_version, licences = self.jats.get_licence_and_article_version_details()
                assert expected_art_vers == article_version

        ##
        ### Test that where no NISO article-version is found within <article-version>, but an old-style specific-use
        ### is set on the <article> element, then that is used.
        ##
        art_vers_set_expected = [
            ## Single article-version
            ("vor", "version of record", "VOR"),
            ("AM", "accepted-manuscript", "AM"),
            ("BAD", "bad", None),
            ## Multiple article-version
            # ([short-form-article-version to set], [long-form-article-version to set],  Expected_article_version returned)
            (["dummy", "VoR"], ["a dummy", "version-of-record"], "VOR"),
            # The following are invalid NISO article-version values
            (["one", "two", "three"], ["one one", "two two", "three three"], None),
        ]

        article_specific_use = "P"
        # Create JATS object with <article specific-use="P"> and no licences
        self._set_jats(article_specific_use, lic_urls_n_specific_uses=[])

        # Test different scenarios of multiple <article-version> nested within <article-version-alternatives>
        for short_art_ver, long_art_ver, expected_art_vers in art_vers_set_expected:
            # If we expect no value from <article-version>, then <article specific-use> value should be used
            expected = expected_art_vers or article_specific_use
            # 1 - Confirm short-form article-version is extracted from <article-version> element text
            # <article-version-alternatives><article-version>XXX</article-version>...</article-version-alternatives>
            # e.g. <article-version>C/EVoR</article-version>
            self._set_jats_article_versions(short_art_ver)
            article_version, licences = self.jats.get_licence_and_article_version_details()
            assert expected == article_version

            # 2 - Confirm long-form article-version is extracted from <article-version> element text
            # <article-version-alternatives><article-version>XXX</article-version>..</article-version-alternatives> element
            # e.g. <article-version>accepted manuscript</article-version>
            self._set_jats_article_versions(long_art_ver)
            article_version, licences = self.jats.get_licence_and_article_version_details()
            assert expected == article_version

    def test_jats_article_version_special_vor_cases(self):
        """
        Confirm that where JATS article version value (coded as <article specific-use="...">) is one of these:
        EVOR, CVOR, C/EVOR and
        1) Where there are no exactly matching license then any VOR licences will be matched
        2) Where exactly matching licences are present, only they  will be extracted from a list of licences
        """
        ##
        ###     Article version is CVOR, EVOR or C/EVOR but no exactly matching licences are present -
        ###     Expect ALL VOR licenses to be returned
        ##

        # 4 licences, have equivalent specific-use values (case insensitive)
        lic_urls_n_specific_uses = [
            (self.BASE_LICENCE + "1", "VoR"),
            (self.BASE_LICENCE + "2", "version-of-record"),
            (self.BASE_LICENCE + "3", "Version of Record"),
            (self.BASE_LICENCE + "4", "Accepted Manuscript"),
            (self.BASE_LICENCE + "5", "AAM"),
        ]

        # Create JATS object with <article specific-use="corrected-version-of-record"> and 3 VOR & 2 AM licences
        self._set_jats("corrected-version-of-record", lic_urls_n_specific_uses=lic_urls_n_specific_uses)
        article_version, licences = self.jats.get_licence_and_article_version_details()
        assert article_version == "CVOR"
        assert len(licences) == 3
        assert licences[0]["specific-use"] == "VOR"     # 1st licence

        # Create JATS object with <article specific-use="enhanced version of record"> and 3 VOR & 2 AM licences
        self._set_jats("enhanced version of record", lic_urls_n_specific_uses=lic_urls_n_specific_uses)
        article_version, licences = self.jats.get_licence_and_article_version_details()
        assert article_version == "EVOR"
        assert len(licences) == 3
        assert licences[1]["specific-use"] == "VOR"     # 2nd licence

        # Create JATS object with <article specific-use="C/EVOR"> and 3 VOR & 2 AM licences
        self._set_jats("C/EVoR", lic_urls_n_specific_uses=lic_urls_n_specific_uses)
        article_version, licences = self.jats.get_licence_and_article_version_details()
        assert article_version == "C/EVOR"
        assert len(licences) == 3
        assert licences[2]["specific-use"] == "VOR"     # 3rd licence

        # Create JATS object with <article specific-use="C/EVOR"> and 3 VOR & 2 AM licences
        self._set_jats("accepted manuscript", lic_urls_n_specific_uses=lic_urls_n_specific_uses)
        article_version, licences = self.jats.get_licence_and_article_version_details()
        assert article_version == "AM"
        assert len(licences) == 2
        assert licences[0]["specific-use"] == "AM"     # 1st licence
        assert licences[1]["specific-use"] == "AM"     # 2nd licence


        ##
        ###     Article version is CVOR, EVOR or C/EVOR - Expect ONLY the matching licence to be returned
        ##

        # 5 licences, 2 are equivalent to "VOR", 1 each equivalent to "EVOR", "CVOR", "C/EVOR" have same specific-use values (case insensitive)
        lic_urls_n_specific_uses = [
            (self.BASE_LICENCE + "1", "VoR"),
            (self.BASE_LICENCE + "2", "version-of-record"),
            (self.BASE_LICENCE + "3", "Corrected Version of Record"),
            (self.BASE_LICENCE + "4", "Enhanced-Version-of-Record"),
            (self.BASE_LICENCE + "5", "C/EVoR")
        ]

        # Create JATS object with <article specific-use="corrected-version-of-record"> and 5 licences
        self._set_jats("corrected-version-of-record", lic_urls_n_specific_uses=lic_urls_n_specific_uses)
        article_version, licences = self.jats.get_licence_and_article_version_details()
        assert article_version == "CVOR"
        assert len(licences) == 1
        assert licences[0]["specific-use"] == "CVOR"


        # Create JATS object with <article specific-use="enhanced version of record"> and 5 licences
        self._set_jats("enhanced version of record", lic_urls_n_specific_uses=lic_urls_n_specific_uses)
        article_version, licences = self.jats.get_licence_and_article_version_details()
        assert article_version == "EVOR"
        assert len(licences) == 1
        assert licences[0]["specific-use"] == "EVOR"

        # Create JATS object with <article specific-use="C/EVOR"> and 5 licences
        self._set_jats("C/EVoR", lic_urls_n_specific_uses=lic_urls_n_specific_uses)
        article_version, licences = self.jats.get_licence_and_article_version_details()
        assert article_version == "C/EVOR"
        assert len(licences) == 1
        assert licences[0]["specific-use"] == "C/EVOR"

