"""
Unit tests for the routing system
"""
# from unittest import TestCase
import os
from copy import deepcopy
from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta
from octopus.lib.paths import get_real_path
from octopus.modules.logger.test_helper import LoggingBufferContext
from octopus.modules.store import store
from router.jper.scheduler import check_unrouted, app_decorator
from router.shared.models import doi_register, note as note_models
from router.shared.models.account import AccOrg
from router.jper.models.repository import MatchProvenance
from router.shared.mysql_dao import NotificationDAO
from router.jper import routing
from router.jper.api import JPER
from router.jper.packages import PackageManager
from tests.jper_tests.fixtures.api import APIFactory
from tests.fixtures.factory import AccountFactory, NotificationFactory
from tests.jper_tests.fixtures.models import PubDepositRecordFactory
from tests.jper_tests.fixtures.packages import PackageFactory
from tests.jper_tests.fixtures.repository import RepositoryFactory
from tests.jper_tests.fixtures.testcase import JPERTestCase

FILES_AND_JATS_PKG = "https://pubrouter.jisc.ac.uk/FilesAndJATS"
SIMPLE_ZIP = "http://purl.org/net/sword/package/SimpleZip"
TEST_FORMAT = "http://router.jisc.ac.uk/packages/OtherTestFormat"

NOTIFICATION_ID = 111

class TestRouting(JPERTestCase):
    @classmethod
    def setUpClass(cls):
        # List the tables (by table name) needed for testing
        cls.tables_for_testing = [
            'account', 'acc_user', 'acc_notes_emails', 'notification', 'notification_account', 'pub_test', 'match_provenance',
            'acc_repo_match_params', 'doi_register', 'pub_deposit', 'metrics', 'h_webservice', 'harvested_unrouted'
        ]
        super().setUpClass()

    @app_decorator
    def test_0_domain_email(self):
        match_set = [
            ("ed.ac.uk", "richard@ed.ac.uk", True),
            ("ed.ac.uk", "richard@phys.ed.ac.uk", True),
            ("physic.ac.uk", "richard@sic.ac.uk", False),
            ("sic.ac.uk/some", "richard@sic.ac.uk", False),
            #("http://www.ic.ac.uk/", "richard@ic.ac.uk", True),#Incorrect test case
            ("http://www.ic.ac.uk/", "richard@ic.ac.uk", False),
            ("sci.ed.ac.uk", "richard@ed.ac.uk", False),
            ("chester.ac.uk", "bad@manchester.ac.uk", False),
            ("chester.ac.uk", "bad@chester.ac.uk.xxx", False),
            ("chester.ac.uk", "ok@chester.ac.uk", True),
        ]
        for (needle, haystack, expected) in match_set:
            m = routing.domain_email(needle, haystack)
            if expected:
                assert isinstance(m, str)
                assert len(m) > 0
            else:
                assert m is False

    @app_decorator
    def test_1_affiliation_domain(self):
        match_set = [
            ("ed.ac.uk", "this is a dummy affiliation richard@ed.ac.uk that might exist", True),
            ("ed.ac.uk", "this is a dummy affiliation richard@phys.ed.ac.uk that might exist", True),
            ("physic.ac.uk", "this is a dummy affiliation richard@sic.ac.uk that might exist", False),
            ("sic.ac.uk/some", "this is a dummy affiliation richard@sic.ac.uk that might exist", False),
            ("http://www.ic.ac.uk/", "this is a dummy affiliation richard@ic.ac.uk that might exist", False),
            ("sci.ed.ac.uk", "this is a dummy affiliation richard@ed.ac.uk that might exist", False),
            ("chester.ac.uk", "this is a dummy affiliation bad@manchester.ac.uk that might exist", False),
            ("chester.ac.uk", "this is a dummy affiliation ok@chester.ac.uk.xxx that might exist", True),
            ("chester.ac.uk", "this is a dummy affiliation ok@chester.ac.uk that might exist", True),
        ]
        for (needle, haystack, expected) in match_set:
            m = routing.affiliation_domain(needle, haystack)
            if expected:
                assert isinstance(m, str)
                assert len(m) > 0
            else:
                assert m is False

    @app_decorator
    def test_2_exact_substring(self):
        match_set = [
            ("boundary", "matches boundary ok", True),
            ("notboundary", "matches this is_notboundary see", False),
            ("this one is not", "in this one", False),
            ("this is the wrong way round", "wrong way", False),
            ("lettERS", "VaryIng CAPITAL LeTTers Not ok", False),
            ("lettERS", "VaryIng CAPITAL lettERS  OK", True),
            ("  lettERS  ", "VaryIng CAPITAL lettERS  OK", False),
        ]
        for (needle, haystack, expected) in match_set:
            m = routing.exact_substring(needle, haystack)
            if expected:
                assert isinstance(m, str)
                assert len(m) > 0
            else:
                assert m is False

    @app_decorator
    def test_3_exact(self):
        match_set = [
            ("richard", "richard", True),
            ("  RICHARD ", "richard   ", False),
            ("Mark", "Richard", False)
        ]
        for (needle, haystack, expected) in match_set:
            m = routing.exact(needle, haystack)
            if expected:
                assert isinstance(m, str)
                assert len(m) > 0
            else:
                assert m is False

    @app_decorator
    def test_4_postcode_match(self):
        match_set = [
            ("HP3 9AA", "HP3 9AA", True),
            ("HP23 1BB", "hp23 1BB", True),
            ("EH10 8YY", "eh108yy", True),
            (" rh6   7PT  ", "rh67pt ", True),
            ("HP45 8IO", "eh9 7uu", False)
        ]
        for (needle, haystack, expected) in match_set:
            m = routing.postcode_match(needle, haystack)
            if expected:
                assert isinstance(m, str)
                assert len(m) > 0
            else:
                assert m is False

    @app_decorator
    def test_5_enhance(self):
        source = NotificationFactory.unrouted_notification()
        # Will use ref just check that elements of the metadata have made it over to the unrouted notification
        # or not as needed, using a reference record to compare the changes
        ref = note_models.UnroutedNotification(source)

        del source["metadata"]["article"]["type"]  # just to check that a field which should get copied over does
        # Remove these to ensure they are re-added by the ehancement process
        del source["metadata"]["license_ref"][0]["type"]
        del source["metadata"]["license_ref"][0]["version"]
        del source["metadata"]["ack"]

        unrouted = note_models.UnroutedNotification(source)

        metadata = note_models.NotificationMetadata(NotificationFactory.notification_metadata())

        unrouted.enhance(metadata)

        # these are the fields that we expect not to have changed
        assert unrouted.article_title == ref.article_title
        assert unrouted.article_version == ref.article_version
        assert unrouted.journal_publishers[0] == ref.journal_publishers[0]
        assert unrouted.journal_title == ref.journal_title
        assert unrouted.article_language[0] == ref.article_language[0]
        assert unrouted.get_publication_date_string() == ref.get_publication_date_string()
        assert unrouted.accepted_date == ref.accepted_date

        # the fields which have taken on the new metadata instead
        assert unrouted.article_type == metadata.article_type

        # Parts of publication date should have changed
        unrouted_pub_date = unrouted.publication_date
        meta_pub_date = metadata.publication_date
        ref_pub_date = ref.publication_date
        for key in ("year", "month", "day"):
            assert ref_pub_date.get(key) is None    # The original didn't have the value
            assert unrouted_pub_date[key] == meta_pub_date[key]   # After enhancement it should have value

        # As metadata and unrouted had one license in common, that should not have been added (but it is used to enhance)
        assert len(unrouted.licenses) == len(ref.licenses) + len(metadata.licenses) - 1
        # Part of license with the latest start date should have changed - as they are sorted, we want the last one
        first_lic = unrouted.licenses[-1]
        meta_lic = metadata.licenses[-1]
        assert first_lic["type"] == meta_lic["type"]
        assert first_lic["version"] == meta_lic["version"]

        # identifier sets that should have changed
        # because ref and metadata share a common DOI article identifier, that will not have been copied during enhancement
        assert len(unrouted.article_identifiers) == len(ref.article_identifiers) + len(metadata.article_identifiers) - 1
        # because ref and metadata share 2 common journal identifiers, they will not have been copied during enhancement
        assert len(unrouted.journal_identifiers) == len(ref.journal_identifiers) + len(metadata.journal_identifiers) - 2

        # changes to author list
        assert len(unrouted.authors) == 3

        unrouted_funder_names = [a.get("name").get("fullname") for a in unrouted.authors]
        counter = 0
        for n in ref.authors:
            assert n.get("name").get("fullname") in unrouted_funder_names
            counter += 1
        assert counter == 2

        counter = 0
        for n in metadata.authors:
            assert n.get("name").get("fullname") in unrouted_funder_names
            counter += 1
        assert counter == 2

        for n in unrouted.authors:
            if n.get("name").get("fullname") == "Richard Jones":
                assert len(n.get("identifier", [])) == 3        # Should have been enhanced with 2nd email address

        # changes to the funding list
        assert len(unrouted.funding) == len(metadata.funding) + 1

        unrouted_funder_names = [a.get("name") for a in unrouted.funding]
        assert len(unrouted_funder_names) == 3
        counter = 0
        for n in ref.funding:
            assert n.get("name") in unrouted_funder_names
            counter += 1
        assert counter == 2

        counter = 0
        for n in metadata.funding:
            assert n.get("name") in unrouted_funder_names
            counter += 1
        assert counter == 2

        # additional subjects
        assert len(unrouted.article_subject) == 5

        # Embargo
        ref_embargo = ref.embargo
        unrouted_embargo = unrouted.embargo
        meta_embargo = metadata.embargo

        assert len(meta_embargo.keys()) == 3
        assert len(ref_embargo.keys()) == 2
        assert len(unrouted_embargo.keys()) == 3
        assert ref_embargo.get("end") is None
        assert unrouted_embargo.get("end") == meta_embargo.get("end")

        assert unrouted.ack == metadata.ack

    @app_decorator
    def test_6_enhance_failures(self):
        source = NotificationFactory.unrouted_notification()
        unrouted = note_models.UnroutedNotification(source)

        # Metadata is identical to source, with some variations
        metadata_source = {"metadata": deepcopy((source["metadata"]))}
        # Change article DOI
        for id_dict in metadata_source["metadata"]["article"]["identifier"]:
            if id_dict["type"] == "doi":
                id_dict["id"] = "Changed-doi"
                break
        # Change pub issn
        for id_dict in metadata_source["metadata"]["journal"]["identifier"]:
            if id_dict["type"] == "issn":
                id_dict["id"] = "Changed-issn"
                break
        # Change publication date year start
        metadata_source["metadata"]["publication_date"]["date"] = "1999-01-01"
        # Change embargo start
        metadata_source["metadata"]["embargo"]["start"] = "1999-09-09"
        # Change part of first licence
        metadata_source["metadata"]["license_ref"][0]["type"] = "Changed"
        metadata = note_models.NotificationMetadata(metadata_source)

        with self.assertRaises(note_models.EnhancementException) as exc:
            unrouted.enhance(metadata)
        assert "In publication_date, the «date» values differ: base (2015-01-01), new (1999-01-01); "\
               "In embargo, the «start» values differ: base (2016-04-01), new (1999-09-09); "\
               "In license_ref, the «type» values differ: base (ccby), new (Changed); "\
               "In journal identifier, the «id» values differ: base (1234-5678), new (Changed-issn); "\
               "In article identifier, the «id» values differ: base (55.aa/base.1), new (Changed-doi)"\
               == str(exc.exception)


    @app_decorator
    def test_7_enhance_authors_projects(self):
        unrouted_source = NotificationFactory.unrouted_notification()
        metadata_source = NotificationFactory.notification_metadata()

        ## 1 - check enhance when NO authors or funding are present at all
        rs = deepcopy(unrouted_source)
        del rs["metadata"]["author"]
        del rs["metadata"]["funding"]
        unrouted = note_models.UnroutedNotification(rs)

        ms = deepcopy(metadata_source)
        del ms["metadata"]["author"]
        del ms["metadata"]["funding"]
        metadata = note_models.NotificationMetadata(ms)

        unrouted.enhance(metadata)

        # check the results
        assert len(unrouted.authors) == 0
        assert len(unrouted.funding) == 0

        ## 2 - check enhance when authors or funding are present in the metadata but NOT the unrouted notification
        rs = deepcopy(unrouted_source)
        del rs["metadata"]["author"]
        del rs["metadata"]["funding"]
        unrouted = note_models.UnroutedNotification(rs)

        ms = deepcopy(metadata_source)
        metadata = note_models.NotificationMetadata(ms)

        unrouted.enhance(metadata)

        # check the results
        assert len(unrouted.authors) == 2
        assert len(unrouted.funding) == 2

        names = [a.get("name").get("fullname") for a in unrouted.authors]
        assert "Richard Jones" in names
        assert "Dave Spiegel" in names

        for auth in unrouted.authors:
            if auth.get("name").get("fullname") == "Richard Jones":
                assert len(auth.get("identifier", [])) == 2
            elif auth.get("name").get("fullname") == "Dave Spiegel":
                assert len(auth.get("identifier", [])) == 2

        names = [f.get("name") for f in unrouted.funding]
        assert "Rotary Club of Eureka" in names
        assert "EPSRC" in names

        for f in unrouted.funding:
            if f.get("name") == "Rotary Club of Eureka":
                assert len(f.get("identifier", [])) == 3
            elif f.get("name") == "EPSRC":
                assert len(f.get("identifier", [])) == 1

        ## 3 - check enhance when authors or funding are present in the unrouted notification but not the metadata
        rs = deepcopy(unrouted_source)
        unrouted = note_models.UnroutedNotification(rs)

        ms = deepcopy(metadata_source)
        del ms["metadata"]["author"]
        del ms["metadata"]["funding"]
        metadata = note_models.NotificationMetadata(ms)

        unrouted.enhance(metadata)

        # check the results
        assert len(unrouted.authors) == 2
        assert len(unrouted.funding) == 2

        names = [a.get("name").get("fullname") for a in unrouted.authors]
        assert "Richard Jones" in names
        assert "Mark MacGillivray" in names

        for auth in unrouted.authors:
            if auth.get("name").get("fullname") == "Richard Jones":
                assert len(auth.get("identifier", [])) == 2
            elif auth.get("name").get("fullname") == "Mark MacGillivray":
                assert len(auth.get("identifier", [])) == 2

        names = [a.get("name") for a in unrouted.funding]
        assert "Rotary Club of Eureka" in names

        for f in unrouted.funding:
            if f.get("name") == "Rotary Club of Eureka":
                assert len(f.get("identifier", [])) == 2

        ## 4 - check enhance when:
        #        - unique authors are present in both cases
        #        - one author record enhances another author record
        unrouted = note_models.UnroutedNotification(deepcopy(unrouted_source))
        unrouted_ref = note_models.UnroutedNotification(deepcopy(unrouted_source))

        metadata = note_models.NotificationMetadata(deepcopy(metadata_source))

        unrouted.enhance(metadata)

        # check the results, compare with reference
        assert len(unrouted.authors) == 3
        assert len(unrouted.authors) == len(unrouted_ref.authors) + 1
        assert len(unrouted.funding) == 3
        assert len(unrouted.funding) == len(unrouted_ref.funding) + 1

        names = [a.get("name").get("fullname") for a in unrouted.authors]
        assert "Richard Jones" in names
        assert "Dave Spiegel" in names
        assert "Mark MacGillivray" in names

        richard_dict = {}
        for auth in unrouted_ref.authors:
            if "Richard Jones" == auth.get("name").get("fullname"):
                richard_dict = {"num_ids": len(auth.get("identifier", [])),
                                "org_name": auth.get("organisation_name"),
                                "aff": auth.get("affiliations")}
                break

        for auth in unrouted.authors:
            if auth.get("name").get("fullname") == "Richard Jones":
                num_ids = len(auth.get("identifier", []))
                assert num_ids == 3
                # Expect 1 email to have been added
                assert num_ids == richard_dict["num_ids"] + 1
                # Expect empty organisation_name in original to have been enhanced
                assert richard_dict["org_name"] == ""
                assert auth.get("organisation_name") == "Alt Metadata Org"
                # Expect affiliation in metadata to have been appended to existing
                enhanced_aff = auth.get("affiliations")
                assert len(enhanced_aff) > len(richard_dict["aff"])
                assert "Alt Metadata Affiliation" not in richard_dict["aff"][0]["raw"]
                assert {"raw": "Alt Metadata Affiliation"} in enhanced_aff
            elif auth.get("name").get("fullname") == "Dave Spiegel":
                assert len(auth.get("identifier", [])) == 2
            elif auth.get("name").get("fullname") == "Mark MacGillivray":
                assert len(auth.get("identifier", [])) == 2

        names = [f.get("name") for f in unrouted.funding]
        assert "Rotary Club of Eureka" in names
        assert "EPSRC" in names

        for f in unrouted.funding:
            if f.get("name") == "Rotary Club of Eureka":
                assert len(f.get("identifier", [])) == 2
            elif f.get("name") == "EPSRC":
                assert len(f.get("identifier", [])) == 1

    @app_decorator
    def test_8_repackage(self):
        # get an unrouted notification to work with
        source = NotificationFactory.unrouted_notification()
        unrouted = note_models.UnroutedNotification(source)
        unrouted.insert()

        custom_zip_path = get_real_path(__file__, "..", "resources", "custom.zip")
        try:
            # put an associated package into the store
            # create a custom zip and get the package manager to ingest
            PackageFactory.make_custom_zip(custom_zip_path, inc_pdf=True)
            PackageManager.ingest(unrouted.id, custom_zip_path, FILES_AND_JATS_PKG)

            # Required package types
            pkg_types = { SIMPLE_ZIP, "https://pubrouter.jisc.ac.uk/PDFUnpacked" }

            links = routing.repackage(unrouted, pkg_types)

            assert len(links) == 3
            assert links[0].get("type") == "package"
            assert links[0].get("format") == "application/zip"
            assert links[0].get("access") == "router"
            assert links[0].get("cloc") == "ArticleFilesJATS.zip"
            assert links[0].get("packaging") == "http://purl.org/net/sword/package/SimpleZip"

            assert links[1].get("type") == "unpackaged"
            assert links[1].get("format") == "application/zip"
            assert links[1].get("access") == "special"
            assert links[1].get("cloc") == f"eprints-rioxx{os.sep}non-pdf-files.zip"
            assert links[1].get("packaging") == "http://purl.org/net/sword/package/SimpleZip"

            assert links[2].get("type") == "unpackaged"
            assert links[2].get("format") == "application/pdf"
            assert links[2].get("access") == "special"
            assert links[2].get("cloc").endswith(".pdf")
        except Exception as e:
            raise e
        finally:
            # This will occur even if exceptions raised in any of the inner try/except blocks was raised above
            try:
                os.remove(custom_zip_path)
            except Exception:
                pass


    @app_decorator
    def test_9_proxy_links(self):
        # get a routed notification to work with
        source = NotificationFactory.routed_notification()
        routed = note_models.RoutedNotification(source)
        l = {
            'url':'http://proxy-link/example.com',
            'access': 'public',
            'type': 'whatever',
            'format': 'whatever',
            'packaging': 'whatever',
            'proxy': 'PROXY-ID'
        }
        routed.add_link_dict(l)
        routed.insert()

        ## Now try retrieving the proxy link for use in proxy_url api call
        proxy_link = JPER.get_proxy_url(routed.id, 'PROXY-ID')
        assert proxy_link == l['url']

    @app_decorator
    def test_10_generate_embargo(self):
        metadata = PackageFactory.get_metadata_from_jats("start_date")
        embargo_end = routing._derive_embargo_from_licenses(metadata.licenses)
        assert embargo_end == "2018-09-20"

    @app_decorator
    def test_11_add_months(self):
        """
        test that the subfunction "add_months" is working as expected in routing.py
        """
        result = routing.add_embargo_months("2018-01-17", 2)
        assert result == "2018-03-17"
        result = routing.add_embargo_months("2018-01", 2)
        assert result == "2018-03-31"
        result = routing.add_embargo_months("2018-01-31", 1)
        assert result == "2018-02-28"
        # check leap years
        result = routing.add_embargo_months("2020-01-31", 1)
        assert result == "2020-02-29"
        result = routing.add_embargo_months("2020-01", 1)
        assert result == "2020-02-29"
        # check string value of months works
        result = routing.add_embargo_months("2018-01", "2")
        assert result == "2018-03-31"
        # check failure cases work as expected
        result = routing.add_embargo_months("2018", 2)
        assert result is None
        result = routing.add_embargo_months("TwentyEighteen", 2)
        assert result is None
        result = routing.add_embargo_months("2018-01", "TwoThousand")
        assert result is None

    @app_decorator
    def test_12_apply_defaults(self):
        """
        ensure that the apply_licence_defaults function in routing.py works as expected
        """
        # setup
        routed_source = NotificationFactory.routed_notification()
        self.pub = AccountFactory.publisher_account()
        self.pub_data = self.pub.publisher_data
        default_embargo_duration = "3"
        self.pub_data.embargo = default_embargo_duration
        pub_date = "2018-01-01"
        # embargoes
        embargo_unknown_end_date = {"end": "9999-12-31", "duration": default_embargo_duration}
        default_embargo_end = routing.add_embargo_months(pub_date, default_embargo_duration)
        embargo_calculated_end_date = {
            "end": default_embargo_end, "start": pub_date, "duration": default_embargo_duration
        }
        # licenses
        default_license = {"title": "default license", "url": "http://default.org", "type": "default", "version": "1"}
        non_open_license = {"title": "not open", "url": "notanopen.org", "type": "closed"}
        open_license_with_start_date = {
            "title": "open", "url": "creativecommons.org", "type": "open", "start": "2019-01-01"
        }
        default_with_no_pub_date = {"title": "This article is under embargo with an end date yet to be finalised"}
        default_with_start_date = deepcopy(default_license)
        default_with_start_date["start"] = default_embargo_end

        self.pub_data.license = default_license
        self.pub.update()

        def _single_test_case(embargo=None, licenses=None, pub_date=None, expected_licenses=None, expected_embargo=None):
            rs = deepcopy(routed_source)
            del rs["metadata"]["embargo"]
            del rs["metadata"]["license_ref"]
            del rs["metadata"]["publication_date"]
            routed = note_models.RoutedNotification(rs)
            routed.provider_id = self.pub.id
            if embargo:
                routed.embargo = {"end": embargo}
            if licenses:
                routed.licenses = licenses
            if pub_date:
                routed.set_publication_date_format(date=pub_date)
            routing.apply_licence_defaults(routed.embargo, routed.licenses, routed, self.pub_data)
            assert routed.embargo == expected_embargo
            assert routed.licenses == expected_licenses

        # pub date, no existing embargo or licensing information- set the default license and embargo as normal
        _single_test_case(
            pub_date=pub_date,
            expected_licenses=[default_with_start_date],
            expected_embargo=embargo_calculated_end_date
        )

        # no pub date, also no existing embargo or licensing information- set a default with unknown embargo end date
        _single_test_case(expected_licenses=[default_with_no_pub_date], expected_embargo=embargo_unknown_end_date)

        # Embargo already exists, but no licence --> expect no change (i.e. no default licence)
        _single_test_case(embargo="2019-01-01", expected_licenses=[], expected_embargo={"end": "2019-01-01"})

        # a license already exists in existing routed info (non open), no default license or embargo set
        _single_test_case(licenses=[non_open_license], expected_licenses=[non_open_license])

        # an open license already exists (with a start date), but no embargo is set
        _single_test_case(
            licenses=[open_license_with_start_date],
            expected_licenses=[open_license_with_start_date],
            expected_embargo={"end": open_license_with_start_date["start"]}
        )

    @app_decorator
    def test_13_match_success_affiliations(self):
        # routing metadata with only a matching "affiliations" field
        source = NotificationFactory.routing_metadata("affiliations")
        md = note_models.RoutingMetadata(source)

        acc = AccountFactory.repo_account(live=True)

        prov = routing.match(md, acc.id, acc.repository_data, RepositoryFactory.repo_config())
        assert prov
        assert len(prov.provenance) == 1

        assert prov.provenance[0]["source_field"] == "name_variants"
        assert prov.provenance[0]["notification_field"] == "affiliations"

    @app_decorator
    def test_14_match_success_domains(self):
        # routing metadata with only a matching "domain" field
        source = NotificationFactory.routing_metadata("domain")
        md = note_models.RoutingMetadata(source)

        acc = AccountFactory.repo_account(live=True)

        prov = routing.match(md, acc.id, acc.repository_data, RepositoryFactory.repo_config())
        assert prov
        assert len(prov.provenance) == 1

        assert prov.provenance[0]["source_field"] == "domains"
        assert prov.provenance[0]["notification_field"] == "emails"

    @app_decorator
    def test_15_match_success_postcodes(self):
        # routing metadata with only a matching "postcodes" field
        source = NotificationFactory.routing_metadata("postcodes")
        md = note_models.RoutingMetadata(source)

        acc = AccountFactory.repo_account(live=True)

        prov = routing.match(md, acc.id, acc.repository_data, RepositoryFactory.repo_config())
        assert prov
        assert len(prov.provenance) == 1

        assert prov.provenance[0]["source_field"] == "postcodes"
        assert prov.provenance[0]["notification_field"] == "postcodes"

    @app_decorator
    def test_16_match_success_grants(self):
        # routing metadata with only a matching "grants" field
        source = NotificationFactory.routing_metadata("grants")
        md = note_models.RoutingMetadata(source)
        acc = AccountFactory.repo_account(live=True)

        prov = routing.match(md, acc.id, acc.repository_data, RepositoryFactory.repo_config())
        assert prov
        assert len(prov.provenance) == 1

        assert prov.provenance[0]["source_field"] == "grants"
        assert prov.provenance[0]["notification_field"] == "grants"

    @app_decorator
    def test_17_match_success_orcids(self):
        # routing metadata with only a matching "orcids" field
        source = NotificationFactory.routing_metadata("orcids")
        md = note_models.RoutingMetadata(source)

        acc = AccountFactory.repo_account(live=True)

        prov = routing.match(md, acc.id, acc.repository_data, RepositoryFactory.repo_config())
        assert prov
        assert len(prov.provenance) == 1

        assert prov.provenance[0]["source_field"] == "author_orcids"
        assert prov.provenance[0]["notification_field"] == "orcids"

    @app_decorator
    def test_18_match_success_emails(self):
        # routing metadata with only a matching "emails" field
        source = NotificationFactory.routing_metadata("emails")
        md = note_models.RoutingMetadata(source)

        acc = AccountFactory.repo_account(live=True)

        prov = routing.match(md, acc.id, acc.repository_data, RepositoryFactory.repo_config())
        assert prov
        assert len(prov.provenance) == 1

        assert prov.provenance[0]["source_field"] == "author_emails"
        assert prov.provenance[0]["notification_field"] == "emails"

    @app_decorator
    def test_19_match_all(self):
        # routing metadata containing every matching field, tests that matching terminates after first match (org_ids)
        source = NotificationFactory.routing_metadata()
        md = note_models.RoutingMetadata(source)

        acc = AccountFactory.repo_account(live=True)

        prov = routing.match(md, acc.id, acc.repository_data, RepositoryFactory.repo_config())
        assert prov
        # only one provenance object (despite there being 6 different matching fields)
        assert len(prov.provenance) == 1
        assert prov.provenance[0]["source_field"] == "org_ids"
        assert prov.provenance[0]["notification_field"] == "org_ids"

    @app_decorator
    def test_20_email_in_affiliation(self):
        # make sure that if a valid domain appears in the affiliation information, then it causes a match
        source = NotificationFactory.routing_metadata("affiliations")
        source["affiliations"] = ["valid_domain@ucl.ac.uk"]
        md = note_models.RoutingMetadata(source)

        acc = AccountFactory.repo_account(live=True)

        prov = routing.match(md, acc.id, acc.repository_data, RepositoryFactory.repo_config())
        assert prov
        assert len(prov.provenance) == 1
        assert prov.provenance[0]["source_field"] == "domains"
        assert prov.provenance[0]["notification_field"] == "affiliations"

    @app_decorator
    def test_21_match_fail(self):
        # example routing metadata from a notification
        source = NotificationFactory.routing_metadata()
        md = note_models.RoutingMetadata(source)

        acc = AccountFactory.repo_account(live=True)

        prov = routing.match(md, acc.id, acc.repository_data, RepositoryFactory.useless_repo_config())
        assert not prov

    @app_decorator
    def test_22_match_age(self):
        source = NotificationFactory.routing_metadata()
        md = note_models.RoutingMetadata(source)
        md.publication_date = "2015-01-01"

        match_config = RepositoryFactory.repo_config()
        acc = AccountFactory.repo_account(live=True)
        acc.repository_data.max_pub_age = 1

        assert not routing.match(md, acc.id, acc.repository_data, match_config)

        md.publication_date = (datetime.today() - relativedelta(month=1, day=1)).strftime("%Y-%m-%d")

        assert routing.match(md, acc.id, acc.repository_data, match_config)

    @app_decorator
    def test_23_routing_against_repo_account_turned_off(self):
        pub = AccountFactory.publisher_account()
        off_account = AccountFactory.repo_account(live=True, matching_config=True)
        # Turn off the account
        off_account.repository_data.repository_off()
        off_account.update()

        notification = APIFactory.incoming_notification_dict(with_content=True)
        filepath = PackageFactory.example_package_path()
        with open(filepath, "rb") as file:
            note = JPER.create_unrouted_note(pub, notification, file)

        unrouted = note_models.UnroutedNotification.pull(note.id)

        successfully_routed = routing.route(unrouted, [], [], AccOrg.get_active_repo_routing_data_tuples())
        assert successfully_routed is False

        assert 0 == len(MatchProvenance.pull_by_notification(unrouted.id))

    @app_decorator
    def test_24a_routing_success_package(self):
        # start a timer so we can check the analysed date later
        now = datetime.now(tz=timezone.utc).replace(microsecond=0)

        # Create Publisher account, which will take simplezip
        pub_acc = AccountFactory.publisher_account()

        # Create Repository account
        repo_acc = AccountFactory.repo_account(live=True, matching_config=True)

        # 2. Creation of metadata + zip content
        notification = APIFactory.incoming_notification_dict(with_content=True, no_links=True)
        del notification["metadata"]["article"]["type"]    # so that we can test later that it gets added with the metadata enhancement
        del notification["metadata"]["peer_reviewed"]       # So can check that apply peer-review default works
        filepath = PackageFactory.example_package_path()
        with open(filepath, "rb") as f:
            note = JPER.create_unrouted_note(pub_acc, notification, f)

        # load the unrouted notification
        urn = note_models.UnroutedNotification.pull(note.id)
        assert len(urn.links) == 0
        assert urn.peer_reviewed is None
        assert urn.has_pdf is True

        # now run the routing algorithm - expect it to succeed
        successfully_routed = routing.route(urn, [], [], AccOrg.get_active_repo_routing_data_tuples())

        assert successfully_routed is True
        links = urn.links
        assert len(links) == 1
        assert links[0]["cloc"] == ""
        assert links[0]["packaging"] == "https://pubrouter.jisc.ac.uk/FilesAndJATS"

        # check that a match provenance was recorded
        mps = MatchProvenance.pull_by_notification(urn.id)
        assert len(mps) == 1, len(mps)

        # check the properties of the match provenance
        mp = mps[0]
        assert mp.repo_id == repo_acc.id
        assert mp.note_id == urn.id
        assert len(mp.provenance) > 0

        # check that a routed notification was created
        rn = note_models.RoutedNotification.pull(urn.id)
        assert rn is not None
        assert rn.analysis_datestamp >= now
        assert repo_acc.id in rn.repositories

        # check that the metadata field we removed gets populated with the data from the package
        assert rn.article_type == "review-article"

        assert rn.peer_reviewed is True     # Default from publisher has been set

        # check the store to see that the conversions were made
        s = store.StoreFactory.get()
        assert s.container_exists(rn.id)

        assert "ArticleFilesJATS.zip" in s.list(rn.id)

        # check the links to be sure that the conversion links were added
        found = False
        for l in rn.links:
            if l.get("cloc") == "ArticleFilesJATS.zip":
                if l.get("packaging") == "http://purl.org/net/sword/package/SimpleZip":
                    found = True
                    break
        assert found

    @app_decorator
    def test_24b_routing_success_no_pdf_package(self):
        # Create Publisher account, which will take simplezip
        pub_acc = AccountFactory.publisher_account()

        # Create Repository account
        repo_acc = AccountFactory.repo_account(live=True, matching_config=True)

        # 2. Creation of metadata + zip content
        notification = APIFactory.incoming_notification_dict(with_content=True, no_links=True)
        del notification["metadata"]

        # "success.zip" filename matches that created by PubDepositRecordFactory.ftp_success() later on
        custom_zip_path = get_real_path(__file__, "..", "resources", "success.zip")
        # put an associated package into the store
        # create a custom zip and get the package manager to ingest
        PackageFactory.make_custom_zip(custom_zip_path, inc_pdf=False)

        with open(custom_zip_path, "rb") as f:
            note = JPER.create_unrouted_note(pub_acc, notification, f)

        # load the unrouted notification
        urn = note_models.UnroutedNotification.pull(note.id)
        assert urn.has_pdf is False

        PubDepositRecordFactory.ftp_success(publisher_id=pub_acc.id, note_id=urn.id)

        log_context = LoggingBufferContext(close_on_exit=True, logger_name="router.jper.app")
        with log_context:
            # now run the routing algorithm - expect it to succeed
            successfully_routed = routing.route(urn, [], [], AccOrg.get_active_repo_routing_data_tuples())
            assert log_context.msg_in_buffer(
                "ERROR_X: route: No PDF file was found in the submitted zip file")

        assert successfully_routed is True
        links = urn.links
        assert len(links) == 1
        assert links[0]["cloc"] == ""
        assert links[0]["packaging"] == "https://pubrouter.jisc.ac.uk/FilesAndJATS"



    @app_decorator
    def test_25_no_routing_bc_no_match_to_account_matching_params(self):
        """
        Where account matching params don't match any of the metadata in the notification, then expect routing will fail.
        :return:
        """
        # useless (won't match) repo config data
        source = RepositoryFactory.useless_repo_config()
        acc = AccountFactory.repo_account(live=True, matching_config=source)

        # get an unrouted notification
        urn = note_models.UnroutedNotification(NotificationFactory.unrouted_notification())
        urn.insert()
        # now run the routing algorithm - expect routing to have failed
        result_obj = check_unrouted()
        total, successfully_routed = result_obj.func_return
        assert total == 1
        assert successfully_routed == 0

        # check that a match provenance was not recorded
        mps = MatchProvenance.pull_by_notification(urn.id)
        assert len(mps) == 0

        # check that a routed notification was not created
        rn = note_models.RoutedNotification.pull(urn.id)
        assert rn is None, rn

    @app_decorator
    def test_26_routing_metadata_test_provider(self):
        """
        Test that test provider is matched (routed) only to Test repo accounts
        :return:
        """
        # start a timer so we can check the analysed date later
        now = datetime.now(tz=timezone.utc).replace(microsecond=0)

        repo_config = RepositoryFactory.repo_config()
        # add an account to the database, which will take simplezip, but there should be no repackaging done as no files
        test_repo_acc = AccountFactory.repo_account(live=False, matching_config=repo_config)

        # Live repo acount is same as test, but with live date set
        live_repo_acc = AccountFactory.repo_account(live=True, matching_config=repo_config)
        # get an unrouted notification (from Publisher) with ID 9
        unrouted = NotificationFactory.unrouted_notification()
        urn = note_models.UnroutedNotification(unrouted)
        urn.insert()
        # Route first notification against Test publisher - should only be routed to the Test repo
        routing.route(urn, test_publishers=[9], test_harvesters=[], active_repo_tuples_list=AccOrg.get_active_repo_routing_data_tuples())

        # check that a match provenance was recorded - should have only matched the Test repository
        mps = MatchProvenance.pull_by_notification(urn.id)
        assert len(mps) == 1

        # check the properties of the match provenance
        mp = mps[0]
        assert mp.repo_id == test_repo_acc.id

        assert mp.note_id == urn.id
        assert len(mp.provenance) > 0

        # check that a routed notification was created and that it doesn't include live repo in list of matched ids
        rn = note_models.RoutedNotification.pull(urn.id)
        assert rn is not None
        assert rn.analysis_datestamp >= now
        assert test_repo_acc.id in rn.repositories
        assert live_repo_acc.id not in rn.repositories

    @app_decorator
    def test_27_routing_metadata_live_provider(self):
        """
        Test that Live provider is matched (routed) to both Live and Test repo accounts
        :return:
        """
        # start a timer so we can check the analysed date later
        now = datetime.now(tz=timezone.utc).replace(microsecond=0)

        repo_config = RepositoryFactory.repo_config()

        # add an account to the database, which will take simplezip, but there should be no repackaging done as no files
        test_repo_acc = AccountFactory.repo_account(live=False, matching_config=repo_config)

        # Live repo acount is same as test, but with live date set
        live_repo_acc = AccountFactory.repo_account(live=True, matching_config=repo_config)

        # get an unrouted notification (from Publisher) with ID 9
        unrouted = NotificationFactory.unrouted_notification()
        urn = note_models.UnroutedNotification(unrouted)
        urn.insert()

        # Route notification against Live  publisher - should be routed to both Live and Test repo
        routing.route(urn, test_publishers=[], test_harvesters=[], active_repo_tuples_list=AccOrg.get_active_repo_routing_data_tuples())

        ## Check results for first notification
        # check that a match provenance was recorded - live provider should have matched to both repos
        mps = MatchProvenance.pull_by_notification(urn.id)
        assert len(mps) == 2

        # check the properties of the match provenance
        mp = mps[0]
        assert len(mp.provenance) > 0

        mp = mps[1]
        assert len(mp.provenance) > 0

        # check that a routed notification was created and that it includes both repos in matched ids
        rn = note_models.RoutedNotification.pull(urn.id)
        assert rn is not None
        assert rn.analysis_datestamp >= now
        assert test_repo_acc.id in rn.repositories
        assert live_repo_acc.id in rn.repositories

    @app_decorator
    def test_28_routing_success_metadata(self):
        # start a timer so we can check the analysed date later
        now = datetime.now(tz=timezone.utc).replace(microsecond=0)

        # add an account to the database, which will take simplezip, but there should be no repackaging done as no files
        acc1 = AccountFactory.repo_account(live=False, matching_config=RepositoryFactory.repo_config())

        # get an unrouted notification
        test_note_dict = NotificationFactory.unrouted_notification()
        unrouted_note = note_models.UnroutedNotification(test_note_dict)
        unrouted_note.insert()

        # now run the routing algorithm
        successfully_routed = routing.route(unrouted_note, [], [], AccOrg.get_active_repo_routing_data_tuples())
        assert successfully_routed is True

        # check that a match provenance was recorded
        match_prov_list = MatchProvenance.pull_by_notification(unrouted_note.id)
        assert len(match_prov_list) == 1, len(match_prov_list)

        # check the properties of the match provenance
        match_prov = match_prov_list[0]
        assert match_prov.repo_id == acc1.id
        assert match_prov.note_id == unrouted_note.id
        assert len(match_prov.provenance) > 0

        # check that a routed notification was created
        routed_note = note_models.RoutedNotification.pull(unrouted_note.id)
        assert routed_note is not None
        assert routed_note.analysis_datestamp >= now
        assert acc1.id in routed_note.repositories

        # No need to check for enhanced metadata as there is no package

        # check the store to be sure that no conversions were made
        s = store.StoreFactory.get()
        assert not s.container_exists(routed_note.id)

    @app_decorator
    def test_29_no_routing_bc_no_match_data(self):
        """
        Check that when a notification contains NO data that can be used for matching (i.e. no authors, contributors or
        funding) that routing does not take place.
        :return:
        """
        # add an account to the database, which will take simplezip, but there should be no repackaging done as no files
        acc = AccountFactory.repo_account(live=False, matching_config=RepositoryFactory.repo_config())

        # get an unrouted notification structure, remove all data that can be used for matching
        # & create unrouted notification object
        test_note_dict = NotificationFactory.unrouted_notification()
        test_note_dict["metadata"]["author"] = []   # Remove all authors
        test_note_dict["metadata"]["contributor"] = []  # Remove all contributors
        test_note_dict["metadata"]["funding"] = []  # Remove all funding
        unrouted_note = note_models.UnroutedNotification(test_note_dict)

        # Confirm that is_sufficient() function returns False in this case
        match_data = unrouted_note.match_data()
        assert match_data.is_sufficient() is False

        # now run the routing algorithm, it should NOT have been routed
        successfully_routed = routing.route(unrouted_note, [], [], AccOrg.get_active_repo_routing_data_tuples())
        assert successfully_routed is False

    @app_decorator
    def test_30_duplicate_doi_routing(self):
        # Add repo account, do NOT allow duplicates from Harvested or Publisher sources (BUT NOTE that FIRST notification
        # from publisher is ALWAYS routed even if a previous (Harvested) notification with same DOI has been received).
        repo_ac1 = AccountFactory.repo_account(live=False,
                                               matching_config=RepositoryFactory.repo_config(),
                                               duplicates_dict={"level_h": 0, "level_p": 0}
                                               )
        # Create dict for 1st unrouted notification (HARVESTED source)
        harv_r2_note_dict = NotificationFactory.unrouted_notification(provider_rank=2)

        # Remove some metadata (make this a "poorer" notification)
        del(harv_r2_note_dict["metadata"]["journal"]["abbrev_title"])
        del(harv_r2_note_dict["metadata"]["journal"]["volume"])
        del(harv_r2_note_dict["metadata"]["article"]["subtitle"])
        del(harv_r2_note_dict["metadata"]["contributor"])
        del(harv_r2_note_dict["metadata"]["funding"][0]["grant_numbers"])
        del(harv_r2_note_dict["metadata"]["funding"][1]["grant_numbers"])

        # Create 1st unrouted notification
        unrouted_harv_r2_note = note_models.UnroutedNotification(harv_r2_note_dict)
        unrouted_harv_r2_note.insert()

        doi = unrouted_harv_r2_note.article_doi

        ##
        ### Preliminary (baseline) checks
        ##
        # Confirm there are no DOI records (empty query defaults to match_all)
        assert doi_register.DoiRegister.count() == 0

        # Confirm there are no Routed
        assert note_models.RoutedNotification.count() == 0

        ##
        ### Run routing - the notification SHOULD BE ROUTED as has never been seen before
        ##
        successfully_routed = routing.route(unrouted_harv_r2_note, [], [], AccOrg.get_active_repo_routing_data_tuples())
        assert successfully_routed is True

        # Should have 1 routed notification
        assert note_models.RoutedNotification.count() == 1

        # After successfully routing should have 1 DOI record, which should show it was routed to the repository account
        doi_recs = doi_register.DoiRegister.pull_all()
        assert len(doi_recs) == 1
        doi_rec = doi_recs[0]
        assert doi_rec.id == doi
        # As this is first notification with this DOI, only the "orig" metrics should be populated ("cum" should not)
        assert doi_rec.get_metrics("orig") is not None
        assert doi_rec.get_metrics("cum") is None
        assert doi_rec.repos == [repo_ac1.id]           # Indicates was routed to repo_ac1 repo account

        ##
        ### Create 2nd notification (PUBLISHER source) & attempt routing - We expect it to route EVEN THOUGH repo_ac1
        ### DOESN'T accept any duplicates (from either source) BECAUSE it is the FIRST publisher notification
        ##
        # Create dict for 2nd unrouted notification
        test_pub_note_dict_2 = NotificationFactory.unrouted_notification()
        # Remove some metadata (make this a "poorer" notification)
        del(test_pub_note_dict_2["metadata"]["journal"]["abbrev_title"])
        del(test_pub_note_dict_2["metadata"]["journal"]["volume"])
        del(test_pub_note_dict_2["metadata"]["article"]["subtitle"])

        unrouted_pub_note = note_models.UnroutedNotification(test_pub_note_dict_2)
        unrouted_pub_note.insert()

        # Expect routing
        successfully_routed = routing.route(unrouted_pub_note, [], [], AccOrg.get_active_repo_routing_data_tuples())
        assert successfully_routed is True
        # Should now have 2 routed notifications
        assert note_models.RoutedNotification.count() == 2

        # Should still have 1 DOI record, but should now have "cum" set.
        doi_recs = doi_register.DoiRegister.pull_all()
        assert len(doi_recs) == 1
        doi_rec_2 = doi_recs[0]
        assert doi_rec_2.id == doi
        # Record should NOT be same as original
        assert doi_rec.data != doi_rec_2.data
        assert doi_rec_2.harv_count == 1
        assert doi_rec_2.pub_count == 1
        orig_metrics = doi_rec_2.get_metrics("orig")
        cumulative_metrics = doi_rec_2.get_metrics("cum")
        assert orig_metrics is not None
        # original metrics should be same as before
        assert orig_metrics == doi_rec.get_metrics("orig")
        assert orig_metrics["n_grant"] == 0

        # cumulative metrics should now be set (from latest notification)
        assert cumulative_metrics is not None
        assert cumulative_metrics["n_grant"] == 2



        ##
        ### Create 3rd notification (2nd from publisher) & attempt routing - expect it NOT to route, because repo_ac1 doesn't accept any duplicates
        ##
        unrouted_pub_note_2 = note_models.UnroutedNotification(test_pub_note_dict_2)
        unrouted_pub_note_2.insert()

        # Expect NO routing
        successfully_routed = routing.route(unrouted_pub_note_2, [], [], AccOrg.get_active_repo_routing_data_tuples())
        assert successfully_routed is False
        # Should still have 2 routed notifications
        assert note_models.RoutedNotification.count() == 2

        # Should still have 1 DOI record, unchanged from previous version
        doi_recs = doi_register.DoiRegister.pull_all()
        assert len(doi_recs) == 1
        doi_rec_3 = doi_recs[0]
        # Should match previous version
        assert doi_rec_3.data == doi_rec_2.data

        ##
        ### Now ENABLE DUPLICATES for Publishers repo_ac1 & attempt to route another notification - expect it NOT to route because only notifications with differences are accepted
        ##
        repo_ac1.repository_data.dups_level_pub = doi_register.DUP_ANY_DIFF
        repo_ac1.update()

        # Create another PUBLISHER notification from test_pub_note_dict_2
        unrouted_pub_note_3 = note_models.UnroutedNotification(test_pub_note_dict_2)
        unrouted_pub_note_3.insert()

        # Routing should occur
        successfully_routed = routing.route(unrouted_pub_note_3, [], [], AccOrg.get_active_repo_routing_data_tuples())
        assert successfully_routed is False
        # Should still have 2 routed notifications
        assert note_models.RoutedNotification.count() == 2

        # Should still have 1 DOI record, unchanged from previous version
        doi_recs = doi_register.DoiRegister.pull_all()
        assert len(doi_recs) == 1
        doi_rec_4 = doi_recs[0]
        # Should match previous version
        assert doi_rec_4.data == doi_rec_3.data

        ##
        ### Now attempt to route another CHANGED notification - expect it to route
        ##
        # Create another PUBLISHER notification
        test_pub_note_dict_3 = NotificationFactory.unrouted_notification()
        unrouted_pub_note_4 = note_models.UnroutedNotification(test_pub_note_dict_3)
        unrouted_pub_note_4.insert()

        # Routing should occur
        successfully_routed = routing.route(unrouted_pub_note_4, [], [], AccOrg.get_active_repo_routing_data_tuples())
        assert successfully_routed is True

        # Should now have 3 routed notification
        assert note_models.RoutedNotification.count() == 3

        # After successfully routing should still have 1 DOI record, but some changes.
        doi_recs = doi_register.DoiRegister.pull_all()
        assert len(doi_recs) == 1
        doi_rec_5 = doi_recs[0]
        assert doi_rec_5.id == doi
        # Record should NOT be same as previous
        assert doi_rec_4.data != doi_rec_5.data
        orig_metrics = doi_rec_5.get_metrics("orig")
        cumulative_metrics = doi_rec_5.get_metrics("cum")
        assert orig_metrics is not None
        # original metrics should be same as before
        assert orig_metrics == doi_rec_4.get_metrics("orig")
        assert orig_metrics["n_grant"] == 0

        # cumulative metrics should now be different (from latest notification)
        assert cumulative_metrics != doi_rec_4.get_metrics("cum")
        assert doi_rec_5.pub_count == 2
        assert doi_rec_5.harv_count == 1

        ##
        ### Now try another Harvested notification (with lower rank) - SHOULD NOT ROUTE as no duplicates allowed from Harvested sources
        ##
        test_harv_r3_note_dict_2 = NotificationFactory.unrouted_notification(provider_rank=3)
        unrouted_harv_r3_note_2 = note_models.UnroutedNotification(test_harv_r3_note_dict_2)
        unrouted_harv_r3_note_2.insert()
        successfully_routed = routing.route(unrouted_harv_r3_note_2, [], [], AccOrg.get_active_repo_routing_data_tuples())
        assert successfully_routed is False

        ##
        ### Now create a SECOND repo account
        ##
        # Add repo account, Do NOT allow duplicates
        repo_ac2 = AccountFactory.repo_account(live=False,
                                               matching_config=RepositoryFactory.repo_config(),
                                               duplicates_dict={"level_h": 0, "level_p": 0}
                                               )

        # Now, AGAIN, try to route the unrouted notification - this time it should be routed ONLY to the new repository
        # (as is not a duplicate for that repo, having never been sent to it previously)
        successfully_routed = routing.route(unrouted_harv_r3_note_2, [], [], AccOrg.get_active_repo_routing_data_tuples())
        assert successfully_routed is True

        # Get the Routed notification created from unrouted notification, it should have been routed ONLY to repo_ac2
        routed_note = note_models.RoutedNotification.pull(unrouted_harv_r3_note_2.id)
        assert routed_note.repositories == [repo_ac2.id]

        # After successfully routing should still have 1 DOI record - the only thing that should have changed are the
        # list of repos which have received this DOI
        doi_recs = doi_register.DoiRegister.pull_all()
        assert len(doi_recs) == 1
        doi_rec_6 = doi_recs[0]

        # Record should NOT be same as previous, but only repos should have changed (with ID of repo_ac2 added to list)
        assert doi_rec_6.data != doi_rec_5.data
        assert doi_rec_6.get_metrics("orig") == doi_rec_5.get_metrics("orig")
        # cumulative metrics should NOT have been updated because notification is "worse" than previous best (worse rank)
        assert doi_rec_6.get_metrics("cum") == doi_rec_5.get_metrics("cum")
        assert doi_rec_6.pub_count == 2
        assert doi_rec_6.harv_count == 2

        # Repos should have been updated to include ID of repo_ac2 (it previously included only ID of repo_ac1)
        latest_repos = doi_rec_6.repos
        assert latest_repos != doi_rec_5.repos
        assert len(latest_repos) == 2
        assert repo_ac1.id in latest_repos
        assert repo_ac2.id in latest_repos

        ##
        ### Now try another Harvested notification  - SHOULD NOT ROUTE as no duplicates allowed from Harvested sources for either repo ac
        ##
        unrouted_harv_r3_note_3 = note_models.UnroutedNotification(test_harv_r3_note_dict_2)
        unrouted_harv_r3_note_3.insert()
        successfully_routed = routing.route(unrouted_harv_r3_note_3, [], [], AccOrg.get_active_repo_routing_data_tuples())
        assert successfully_routed is False

        ##
        ### Now Change BOTH 1st & 2nd accounts to allow all Harvested duplicates
        ### And try the same Harvested notification - This time it SHOULD ROUTE to both repo accs
        ##
        repo_ac1.repository_data.dups_level_harv = doi_register.DUP_ALL
        repo_ac1.update()
        repo_ac2.repository_data.dups_level_harv = doi_register.DUP_ALL
        repo_ac2.update()

        successfully_routed = routing.route(unrouted_harv_r3_note_3, [], [], AccOrg.get_active_repo_routing_data_tuples())
        assert successfully_routed is True

        # Check the note was routed to BOTH accounts
        routed_note = note_models.RoutedNotification.pull(unrouted_harv_r3_note_3.id)
        assert sorted(routed_note.repositories) == [repo_ac1.id, repo_ac2.id]

        # After successfully routing should still have 1 DOI record - nothing should have changed apart from `h_count`
        doi_recs = doi_register.DoiRegister.pull_all()
        assert len(doi_recs) == 1
        doi_rec_7 = doi_recs[0]
        assert doi_rec_7.harv_count == doi_rec_6.harv_count + 1
        assert doi_rec_7.get_metrics("orig") == doi_rec_6.get_metrics("orig")
        # cumulative metrics should NOT have been updated because notification is "worse" than previous best (worse rank)
        assert doi_rec_7.get_metrics("cum") == doi_rec_6.get_metrics("cum")
        assert doi_rec_7.pub_count == 2
        assert doi_rec_7.harv_count == 3


    @app_decorator
    def test_31_mixture_success_failure(self):
        """
        Check that where some notifications match & other's don't the matched notifications are converted to Routed
        and the unmatched are deleted.
        :return:
        """
        # start a timer so we can check the analysed date later
        now = datetime.now(tz=timezone.utc).replace(microsecond=0)

        # Create Publisher account, which will take simplezip
        pub_acc = AccountFactory.publisher_account()

        # useless (won't match) repo config data
        repo_ac_match_none = AccountFactory.repo_account(
            live=True,
            matching_config=RepositoryFactory.useless_repo_config())

        # Create Repository account, that matches notification with author affiliation: "University of Life"
        repo_ac_match_life = AccountFactory.repo_account(
            live=True,
            matching_config={"domains": [],
                             "name_variants": ["University of Life"],
                             "orcids": [],
                             "emails": [],
                             "postcodes": []})

        # Create notification - metadata + zip content
        note_dict = APIFactory.incoming_notification_dict(with_content=True)
        del note_dict["links"]
        del note_dict["metadata"]["article"]["type"]    # so that we can test later that it gets added with the metadata enhancement
        filepath = PackageFactory.example_package_path()
        with open(filepath, "rb") as f:
            note_with_content = JPER.create_unrouted_note(pub_acc, note_dict, f)

        # Create notification with content that WON'T match any account
        # Now amend authors so won't match any account & create 2nd notification
        note_dict["metadata"]["author"] = [{
            "type": "corresp",
            "name": {
                "firstname": "Johnny",
                "surname": "Nomatch",
                "fullname": "Johnny Nomatch"
            },
            "organisation_name": "Somewhere",
            "identifier": [],
            "affiliations": [{"raw": "Anywhere but here"}]
        }]
        with open(filepath, "rb") as f:
            nomatch_note_with_content = JPER.create_unrouted_note(pub_acc, note_dict, f)

        # load the unrouted notifications
        urn = note_models.UnroutedNotification.pull(note_with_content.id)
        assert len(urn.links) == 0
        nomatch_urn = note_models.UnroutedNotification.pull(nomatch_note_with_content.id)
        assert len(nomatch_urn.links) == 0

        s = store.StoreFactory.get()
        # check the store to see that files are stored for both of the notifications
        assert s.container_exists(urn.id)
        assert s.container_exists(nomatch_urn.id)


        assert 2 == note_models.UnroutedNotification.count()
        assert 0 == note_models.RoutedNotification.count()
        assert 2 == NotificationDAO.count()     # All notifications

        # now run the routing algorithm - expect it to succeed
        result_obj = check_unrouted()
        total, num_routed = result_obj.func_return
        assert total == 2
        assert num_routed == 1

        s = store.StoreFactory.get()
        # check the store to see that article files are still stored for Routed notification
        assert s.container_exists(urn.id)
        # check the store to see that Unrouted notification article file has been DELEtED (NO longer exists)
        assert not s.container_exists(nomatch_urn.id)

        # ALl unrouted should have been deleted
        assert 0 == note_models.UnroutedNotification.count()
        assert 1 == note_models.RoutedNotification.count()
        assert 1 == NotificationDAO.count()     # All notifications

        # check that a match provenance was recorded for just one notification
        assert 1 == MatchProvenance.count()
        mps = MatchProvenance.pull_by_notification(urn.id)
        assert len(mps) == 1, len(mps)

        # check the properties of the match provenance
        mp = mps[0]
        assert mp.repo_id == repo_ac_match_life.id
        assert mp.note_id == urn.id
        assert len(mp.provenance) > 0

        # check that a routed notification was created
        rn = note_models.RoutedNotification.pull(urn.id)
        assert rn is not None
        assert rn.analysis_datestamp >= now
        assert repo_ac_match_life.id in rn.repositories

        # check that the metadata field we removed gets populated with the data from the package
        assert rn.article_type == "review-article"
        # check the links to be sure that the conversion links were added
        found = False
        for l in rn.links:
            if l.get("cloc") == "ArticleFilesJATS.zip":
                if l.get("packaging") == "http://purl.org/net/sword/package/SimpleZip":
                    found = True
                    break
        assert found

    @app_decorator
    def test_32_match_success_org_ids(self):
        # routing metadata with only a matching "org_ids" field
        source = NotificationFactory.routing_metadata("org_ids")
        md = note_models.RoutingMetadata(source)

        acc = AccountFactory.repo_account(live=True)

        prov = routing.match(md, acc.id, acc.repository_data, RepositoryFactory.repo_config())
        assert prov
        assert len(prov.provenance) == 1

        assert prov.provenance[0]["source_field"] == "org_ids"
        assert prov.provenance[0]["notification_field"] == "org_ids"

    @app_decorator
    def test_33_strip_tags_from_harvested_notifications(self):
        """
        Test that for a harvested notification, any XML tags are removed from within these fields:
            article title, article_abstract, journal title, acknowledgement

        :return:
        """

        # start a timer so we can check the analysed date later
        now = datetime.now(tz=timezone.utc).replace(microsecond=0)

        # add an account to the database, which will take simplezip, but there should be no repackaging done as no files
        acc1 = AccountFactory.repo_account(live=False, matching_config=RepositoryFactory.repo_config())

        # Create an unrouted Harvester notification
        orig_note_dict = NotificationFactory.unrouted_notification(provider_rank=3)
        test_note_dict = deepcopy(orig_note_dict)
        test_note_dict["metadata"]["ack"] = "<test attrib=\"xyz\"> ACKNOWLEDGEMENT </test> " + orig_note_dict["metadata"]["ack"] + "<end:thing attrib=\"xyz\"> TAG-TEXT </end:thing>"
        test_note_dict["metadata"]["journal"]["title"] = "<journal_title attrib=\"xyz\"> TAG-TEXT </journal_title> " + orig_note_dict["metadata"]["journal"]["title"] + "<end:thing attrib=\"xyz\"> TAG-TEXT </end:thing>"
        test_note_dict["metadata"]["article"]["title"] = "<article_title attrib=\"xyz\"> TAG-TEXT </article_title> " + orig_note_dict["metadata"]["article"]["title"] + "<end:thing attrib=\"xyz\"> TAG-TEXT </end:thing>"
        test_note_dict["metadata"]["article"]["abstract"] = "<abstract attrib=\"xyz\"> ABSTRACT </abstract> " + orig_note_dict["metadata"]["article"]["abstract"] + "<end:thing attrib=\"xyz\"> TAG-TEXT </end:thing>"
        harvested_note = note_models.HarvestedNotification(test_note_dict)
        harvested_note.insert()

        # now run the routing algorithm
        successfully_routed = routing.route(harvested_note, [], [], AccOrg.get_active_repo_routing_data_tuples())
        assert successfully_routed is True

        # check that a match provenance was recorded
        match_prov_list = MatchProvenance.pull_by_notification(harvested_note.id)
        assert len(match_prov_list) == 1, len(match_prov_list)

        # check the properties of the match provenance
        match_prov = match_prov_list[0]
        assert match_prov.repo_id == acc1.id
        # assert match_prov.note_id == harvested_note.id
        assert len(match_prov.provenance) > 0

        # check that a routed notification was created
        routed_note = note_models.RoutedNotification.pull(match_prov.note_id)
        assert routed_note is not None
        assert routed_note.analysis_datestamp >= now
        assert acc1.id in routed_note.repositories

        # Check that TAGS have been removed
        assert routed_note.ack == orig_note_dict["metadata"]["ack"] + " TAG-TEXT"   # NB. "ACKNOWLEDGEMENT" prefix should have been removed
        assert routed_note.journal_title == "TAG-TEXT " + orig_note_dict["metadata"]["journal"]["title"] + " TAG-TEXT"
        assert routed_note.article_title == "TAG-TEXT " + orig_note_dict["metadata"]["article"]["title"] + " TAG-TEXT"
        assert routed_note.article_abstract == orig_note_dict["metadata"]["article"]["abstract"] + " TAG-TEXT"  # NB. "ABSTRACT" prefix should have been removed
