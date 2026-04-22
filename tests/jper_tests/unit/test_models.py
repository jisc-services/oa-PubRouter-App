"""
Unit tests for the core system objects
"""
from copy import deepcopy

from octopus.lib.random import random_alphanumeric_string
from octopus.lib.dates import now_str
from octopus.lib import dataobj

from router.shared.models.account import AccOrg, AccRepoMatchParams, AccUser
from router.shared.models import note as note_models
from router.jper.app import app_decorator
from router.jper.models.identifier import Identifier
from router.jper.models.publisher import FTPDepositRecord
from router.jper.models.repository import MatchProvenance

from tests.jper_tests.fixtures.api import APIFactory
from tests.jper_tests.fixtures.cms_models import CMSFactory, CmsMgtCtl, CmsHtml
from tests.jper_tests.fixtures.repository import RepositoryFactory
from tests.jper_tests.fixtures.models import PubDepositRecordFactory, IdentifierFactory
from tests.jper_tests.fixtures.testcase import JPERTestCase
from tests.fixtures.factory import AccountFactory, NotificationFactory

class TestModels(JPERTestCase):

    @classmethod
    def setUpClass(cls):
        # List the tables (by table name) needed for testing
        cls.tables_for_testing = [
            'account', 'acc_user', 'acc_repo_match_params', 'notification', 'match_provenance', 'pub_deposit',
            'org_identifiers', 'cms_ctl', 'cms_html'
        ]
        super().setUpClass()

    @staticmethod
    def create_author_with_emails_in_aff(full_name, auth_dict, emails, id_email=None):
        _auth_dict = deepcopy(auth_dict)
        first, space, last = full_name.partition(" ")
        _auth_dict["name"] = {
            "firstname": first,
            "surname": last,
            "fullname": full_name
        }
        # If an id_email was passed then add as identifier
        if id_email:
            _auth_dict["identifier"].append({"type": "email", "id": id_email})

        affilation_string = ""
        for email in emails:
            affilation_string += f" {random_alphanumeric_string(30)} {email}"
        _auth_dict["affiliations"] = [{"raw": affilation_string}]
        return _auth_dict

    @app_decorator
    def test_unrouted(self):
        # just try making one from scratch
        unrouted = note_models.UnroutedNotification()

        # now try building one from a complete data structure
        source = NotificationFactory.unrouted_notification(no_id_or_created=True)
        unrouted = note_models.UnroutedNotification(source)

        # just check the properties are retrievable
        assert unrouted.id is None
        # check that we can write/read
        unrouted.insert(reload=True)

        pulled_unrouted = note_models.UnroutedNotification.pull(unrouted.id)
        assert pulled_unrouted.data == unrouted.data

        # test using harness
        dataobj.test_dataobj(note_models.UnroutedNotification, source)


    @app_decorator
    def test_routed(self):
        # try making one from scratch
        rn = note_models.RoutedNotification()

        # try building one from a complete datastructure
        source = NotificationFactory.routed_notification(no_id_or_created=True)
        rn = note_models.RoutedNotification(source)

        assert rn.id is None
        assert rn.created is None
        assert rn.packaging_format == "https://pubrouter.jisc.ac.uk/FilesAndJATS"

        # check that we can write/read
        rn.insert(reload=True)  # Need to update the created-date set by database NB. reload only needed during testing
                                # As in live running once a routed notifiation is saved it is not updated again.
        assert rn.id is not None
        assert rn.created is not None

        rn2 = note_models.RoutedNotification.pull(rn.id)
        assert rn2.data == rn.data

        # test using harness
        dataobj.test_dataobj(note_models.RoutedNotification, source)

    @app_decorator
    def test_routing_meta(self):
        # make one from scratch
        note_models.RoutingMetadata()

        # build one from an example document
        source = NotificationFactory.routing_metadata()
        note_models.RoutingMetadata(source)

        # Note: at this point we don't serialise routing metadata, it's an in-memory model only

    @app_decorator
    def test_repository_config_remove_redundancies(self):
        # check that remove_redundancies works as expected

        # make a config including redundant parameters
        matching_config = RepositoryFactory.duplicate_repo_config()

        matching_parameters = AccRepoMatchParams({"id": 123, "matching_config": matching_config})
        # remove redundancies
        matching_parameters.remove_redundant_matching_params_and_sort()

        # the origin config (without redundancies)
        origin_config = RepositoryFactory.repo_config()

        assert sorted(matching_parameters.domains, key=len) == sorted(origin_config["domains"], key=len)
        assert sorted(matching_parameters.name_variants, key=len) == sorted(origin_config["name_variants"], key=len)
        assert matching_parameters.author_orcids == sorted(origin_config["orcids"])
        assert matching_parameters.grants == sorted(origin_config["grants"])
        assert matching_parameters.postcodes == sorted(origin_config["postcodes"])
        assert matching_parameters.org_ids == sorted(origin_config["org_ids"])

    @app_decorator
    def test_match_provenance(self):
        # make one from scratch
        mp = MatchProvenance()

        # build one from example document
        source = RepositoryFactory.match_provenance()
        mp = MatchProvenance(source)

        # check that we can write/read
        mp.insert()

        mp_retrieved = MatchProvenance.pull(mp.note_id, mp.repo_id)
        del(mp_retrieved.data["created"])     # Remove created date which is added by MySQL when rec is inserted
        assert mp_retrieved.data == mp.data

    @app_decorator
    def test_incoming_notification(self):
        # make one from scratch
        incoming = note_models.IncomingNotification()
        # build one from example document
        source = APIFactory.incoming_notification_dict()
        # Make dates UTC format (they should be converted to YYYY-MM-DD format)
        orig = deepcopy(source)
        orig_metadata = orig["metadata"]
        source_metadata = source["metadata"]
        source_metadata["accepted_date"] += "T18:00:41Z"
        source_metadata["publication_date"]["date"] += "T18:00:41Z"
        source_metadata["history_date"][0]["date"] += "T18:00:41Z"
        source_metadata["embargo"]["end"] += "T18:00:41Z"
        source_metadata["embargo"]["start"] += "T18:00:41Z"
        source_metadata["license_ref"][0]["start"] += "T18:00:41Z"
        incoming = note_models.IncomingNotification(source)
        in_metadata = incoming.data["metadata"]
        assert in_metadata["accepted_date"] == orig_metadata["accepted_date"]
        assert in_metadata["publication_date"]["date"] == orig_metadata["publication_date"]["date"]
        assert in_metadata["history_date"][0]["date"] == orig_metadata["history_date"][0]["date"]
        assert in_metadata["embargo"]["end"] == orig_metadata["embargo"]["end"]
        assert in_metadata["embargo"]["start"] == orig_metadata["embargo"]["start"]
        assert in_metadata["license_ref"][0]["start"] == orig_metadata["license_ref"][0]["start"]

        # request an unrouted notification
        ur = incoming.make_unrouted()
        assert isinstance(ur, note_models.UnroutedNotification)

        # test using harness
        dataobj.test_dataobj(note_models.UnroutedNotification, source)

    @app_decorator
    def test_outgoing_notification(self):
        # make one from scratch
        note_models.OutgoingNotification()

        # build one from example document
        source = APIFactory.outgoing_notification_dict()
        outgoing = note_models.OutgoingNotification(source)

        source["id"] = outgoing.id
        # test using harness
        dataobj.test_dataobj(note_models.OutgoingNotification, source)

    def _check_outgoing_licenses_and_provider(self, src_note, out_note):
        """
        Test that Outgoing licenses have had the "best" license flag added and that
        provider information has been restricted for OutgoingNotification

        :param src_note:    Source notification (routed or unrouted)
        :param out_note:    OutgoingNotification
        :return: nothing
        """

        # Check licenses are as expected
        src_licenses = src_note.licenses
        out_licenses = out_note.licenses
        assert len(src_licenses) == len(out_licenses)

        # If we have more than one license and none has a URL then we expect all of the licenses to have "best" set to False
        # If there is just 1 license, or at least 1 license has a URL, then expect just 1 license to be set True
        expected_best = 0
        num_best = 0
        for (ix, out_lic) in enumerate(out_licenses):
            src_lic = src_licenses[ix]
            # Outgoing licenses should have the "best" key added
            assert len(out_lic.keys()) == len(src_lic.keys()) + 1
            # If any of the source licenses has a URL then we will expect 1 "best" license
            if src_lic.get("url"):
                expected_best = 1
            if out_lic.get("best"):
                num_best += 1
        # No license had a URL and there is only 1 license
        if expected_best == 0 and len(src_licenses) == 1:
            expected_best = 1
        # Number of best licenses should not exceed 1
        assert num_best == expected_best

        # Check provider info is as expected depending on notification type
        if isinstance(out_note, note_models.OutgoingNotification):
            # Should only have provider.agent set
            assert out_note.provider_agent is not None
            assert len(out_note.data.get("provider")) == 1
        else:
            # can have additional fields, at least the provider.route
            assert out_note.provider_route is not None
            assert len(out_note.data.get("provider")) > 1

    @app_decorator
    def test_routed_outgoing(self):
        # create an unrouted notification to work with
        source = NotificationFactory.routed_notification(no_id_or_created=True)
        routed_note = note_models.RoutedNotification(source)
        routed_note.insert()

        # get an ordinary outgoing notification (v3)
        out = routed_note.make_outgoing()
        assert isinstance(out, note_models.OutgoingNotification)
        assert len(out.links) == 6
        self._check_outgoing_licenses_and_provider(routed_note, out)
        # details of repositories routed to should have been removed
        assert out.repositories == []
        # Test Funding is as expected
        # First funding element in routed_note and outgoing note should be identical
        assert routed_note.funding[0] == out.funding[0]
        # For second funding element, the outgoing note should have had Non-URI identifiers converted to URIs
        for routed_id_dict in routed_note.funding[1]["identifier"]:
            # original IDs are NOT URIs
            assert not routed_id_dict.get("id").startswith("http")
        for out_id_dict in out.funding[1]["identifier"]:
            # Outgoing IDs ARE URIs
            assert out_id_dict.get("id").startswith("https")

    @app_decorator
    def test_unrouted_match_data(self):
        """
        Confirm that RoutingMetadata (match data) is correctly extracted from the unrouted notification - this should
        be derived only from authors (not contributors).

        :return:
        """
        source = NotificationFactory.unrouted_notification()
        urn = note_models.UnroutedNotification(source)
        md = urn.match_data()

        assert len(md.emails) == 2
        assert "richard@example.com" in md.emails
        assert "mark@example.com" in md.emails
        assert len(md.affiliations) == 2
        assert "Cottage Labs org, Moonshine dept, Lame street, Cardiff, Gwent, HP3 9AA, England, ISNI: isni 1111 2222 3333, ROR: ror-123" in md.affiliations
        assert "Cottage Labs, EH9 5TP" in md.affiliations
        orcids = md.orcids
        assert len(orcids) == 2
        assert '0000-0002-4797-908X' in orcids
        assert '0000-0002-0136-3706' in orcids
        assert len(md.postcodes) == 2
        assert "HP3 9AA" in md.postcodes
        assert "EH9 5TP" in md.postcodes
        assert sorted(['BB/34/juwef', 'wellcome-grant']) == sorted(md.grants)
        assert len(md.org_ids) == 2
        assert 'ISNI:isni111122223333' in md.org_ids
        assert 'ROR:ror-123' in md.org_ids

    @app_decorator
    def test_live_repos(self):
        AccountFactory.create_all_account_types(org_only=True)
        live_accounts = AccOrg.get_repositories("L")
        assert len(live_accounts) == 1

    @app_decorator
    def test_publishers(self):
        AccountFactory.create_all_account_types(org_only=True)
        publishers = AccOrg.get_publishers()
        assert len(publishers) == 2

    @app_decorator
    def test_active_accounts(self):
        initial_accs = AccOrg.get_all_undeleted_accounts_of_type()
        # Create all types of account - one is deleted
        num_org_acs, _ = AccountFactory.create_all_account_types(org_only=True)
        active_accounts = AccOrg.get_all_undeleted_accounts_of_type()
        expected_num_acs = len(initial_accs) + num_org_acs - 1    # subtract 1 deleted ac
        assert len(active_accounts) == expected_num_acs

    @app_decorator
    def test_ftp_records(self):
        error = PubDepositRecordFactory.ftp_error(publisher_id=2, note_id=7)
        success = PubDepositRecordFactory.ftp_success(publisher_id=3, note_id=8)
        assert len(FTPDepositRecord.get_all_from_publisher(error.publisher_id)) == 1
        assert FTPDepositRecord.get_by_notification_id(error.notification_id) is not None
        PubDepositRecordFactory.ftp_success(publisher_id=success.publisher_id)
        assert len(FTPDepositRecord.get_all_from_publisher(success.publisher_id)) == 2

    @app_decorator
    def test_ftp_records_aggregations(self):
        first_record = PubDepositRecordFactory.ftp_success(publisher_id=33, note_id=88)
        pub_id = first_record.id
        for x in range(8):
            PubDepositRecordFactory.ftp_success(publisher_id=pub_id, note_id=x+1)
        for x in range(2):
            PubDepositRecordFactory.ftp_error(publisher_id=pub_id, note_id=x+20)
        all_recs = FTPDepositRecord.get_all_from_publisher(pub_id)
        assert len(all_recs) == 10
        total_count, scroller, col_headings = FTPDepositRecord.aggregate_pub_deposit_daily(pub_id)
        assert total_count == 1
        with scroller:
            first_rec = next(scroller)
        # Each tuple (Date, Total, OK, Matched, Matched-live, Files, Error Messages, Type)
        _date, type, total, successful, matched, matched_live, files, errors = first_rec
        assert successful == 8
        assert files == "error.zip|error.zip"
        assert errors == "error.zip – error|error.zip – error"

    @app_decorator
    def test_ftp_records_total_buckets(self):
        publisher = AccountFactory.publisher_account()
        PubDepositRecordFactory.make_many_ftp_success_records(publisher.id)
        total_count, scroller, col_headings = FTPDepositRecord.aggregate_pub_deposit_daily(publisher.id)
        assert total_count == 1
        with scroller:
            tuple_list = list(scroller)
        assert len(tuple_list) == 1
        assert tuple_list[0][2] == 30

    @app_decorator
    def test_ftp_records_dict_keys(self):
        publisher = AccountFactory.publisher_account()
        for x in range(8):
            PubDepositRecordFactory.ftp_success(publisher_id=publisher.id, note_id=x+1)
        for x in range(2):
            PubDepositRecordFactory.ftp_error(publisher_id=publisher.id, note_id=x+20)
        total_count, scroller, col_headings = FTPDepositRecord.recs_scroller_for_csv_file(publisher.id)
        assert scroller
        with scroller:
            csv_list = list(scroller)
        csv_row = csv_list[0]
        assert col_headings == ["Date", "Type", "Total", "Successful", "Matched", "Error Files", "Error Messages"]
        assert csv_row[2] == 10
        assert csv_row[3] == 8
        assert csv_row[5] == "error.zip, error.zip"
        assert csv_row[6] == "error.zip – error, error.zip – error"

    @app_decorator
    def test_account_identifiers(self):
        account_repo_data = AccountFactory.repo_account(live=True).repository_data
        assert account_repo_data.identifiers == []
        account_repo_data.jisc_id = "JISC"
        expected = [{"type": "JISC", "id": "JISC"}]
        assert account_repo_data.identifiers == expected
        assert account_repo_data.jisc_id == "JISC"
        account_repo_data.core_id = "CORE"
        expected.append({"type": "CORE", "id": "CORE"})
        assert account_repo_data.identifiers == expected
        assert account_repo_data.core_id == "CORE"

        account_repo_data.update()
        assert account_repo_data.identifiers == expected
        assert account_repo_data.core_id == "CORE"
        assert account_repo_data.jisc_id == "JISC"
        account_repo_data.jisc_id = "NotJISC"
        assert account_repo_data.jisc_id == "NotJISC"

    @app_decorator
    def test_identifier_searching(self):
        uni_name = "University of Whacko"
        other_name = "Hello World"
        IdentifierFactory.make_jisc(uni_name)
        IdentifierFactory.make_core(uni_name)

        assert Identifier.count() == 2
        assert len(Identifier.search_by_name("University")) == 2
        assert len(Identifier.search_by_name("University", "JISC")) == 1
        assert len(Identifier.search_by_name("University", "CORE")) == 1

        IdentifierFactory.make_jisc(other_name)
        IdentifierFactory.make_core(other_name)

        assert len(Identifier.search_by_name("Hello")) == 2
        assert len(Identifier.search_by_name("Hello", "JISC")) == 1
        assert len(Identifier.search_by_name("Hello", "CORE")) == 1

    @app_decorator
    def test_delete_identifier_by_type(self):
        IdentifierFactory.make_jisc("Some Name")
        IdentifierFactory.make_core("Some Name")
        assert Identifier.count() == 2

        Identifier.delete_all_by_type("JISC")
        assert Identifier.count() == 1

    @app_decorator
    def test_identifier_reload_with_2_col_iterator(self):
        # Simulate CSV file with 2 columns: Id, Name
        iterator = [
            (),  # Empty row should be ignored
            ("ID", "Name"),
            ("12345", "University of Whacko"),
            (),  # Empty row should be ignored
            ("6789", "Hello World")
        ]
        Identifier.reload_type_by_identifier_iterable(iterator, "JISC")
        Identifier.reload_type_by_identifier_iterable(iterator, "CORE")
        assert Identifier.count() == 4

        iterator.append(("3456", "University of Amazing"))
        Identifier.reload_type_by_identifier_iterable(iterator, "JISC")
        assert Identifier.count() == 5
        all_ids = Identifier.pull_all(wrap=False)
        assert len(all_ids) == 5
        # Confirm that ID's have been loaded into 'value' column
        first_id = all_ids[0]
        assert first_id["type"] in ("JISC", "CORE")
        assert first_id["value"].isdigit()

        # CHANGE ORDER OF DATA....
        # Simulate CSV file with 2 columns: Name, ID
        iterator = [
            ("Name", "ID"),
            ("University of Whacko", "12345"),
            ("Hello World", "456")
        ]
        Identifier.truncate_table()
        Identifier.reload_type_by_identifier_iterable(iterator, "SPAM")
        all_ids = Identifier.pull_all(wrap=False)
        assert len(all_ids) == 2
        first_id = all_ids[0]
        assert first_id["type"] == "SPAM"
        assert first_id["value"].isdigit()

    @app_decorator
    def test_identifier_reload_with_3_col_iterator(self):
        # Simulate CSV file with 3 columns: Type, Name, Id
        iterator = [
            ("TYPE", "Name", "ID"),
            ("JISC", "University of Whacko", "12345"),
            ("JISC", "Hello World", "6789"),
            (), # Empty row should be ignored
            ("CORE", "University of Whacko", "12345"),
            ("CORE", "Hello World", "6789"),
            ("SPAM", "**Not loaded**", "9999")
        ]
        num_loaded = Identifier.reload_type_by_identifier_iterable(iterator, "JISC")
        assert num_loaded == 2
        assert Identifier.count() == 2
        num_loaded = Identifier.reload_type_by_identifier_iterable(iterator, "CORE")
        assert num_loaded == 2
        assert Identifier.count() == 4

        iterator.append(("JISC", "University of Amazing", "3456"))
        num_loaded = Identifier.reload_type_by_identifier_iterable(iterator, "JISC")
        assert num_loaded == 3
        assert Identifier.count() == 5
        all_ids = Identifier.pull_all(wrap=False)
        assert len(all_ids) == 5
        # Confirm that ID is loaded into value column
        first_id = all_ids[0]
        assert first_id["type"] in ("JISC", "CORE")
        assert first_id["value"].isdigit()

    @app_decorator
    def test_identifier_reload_with_bad_data_iterator(self):
        # Simulate CSV file with 3 columns: Type, Name, Id - BUT Missing an id
        iterator = [
            ("Filename row"),
            ("TYPE", "Name", "ID"),
            ("JISC", "Hello World", "789"),
            (),     # Empty row
            ("JISC", "University of No ID")
        ]
        with self.assertRaises(ValueError) as exc:
            num_loaded = Identifier.reload_type_by_identifier_iterable(iterator, "JISC")
        assert "Got fewer than 2 mandatory elements in the row" in str(exc.exception)


        # Simulate CSV file with 3 columns: Type, Name, Id - BUT Missing a name
        iterator = [
            ("Filename row"),
            ("ID", "TYPE", "Name"),
            ("789", "JISC", "Hello World"),
            (),     # Empty row
            ("1232", "JISC")
        ]
        with self.assertRaises(ValueError) as exc:
            num_loaded = Identifier.reload_type_by_identifier_iterable(iterator, "JISC")
        assert "Got fewer than 2 mandatory elements in the row" in str(exc.exception)


        # Simulate CSV file with 3 columns: Type, Name, Id - BUT NO valid numeric ID
        iterator = [
            ("Filename row"),
            ("TYPE", "Name", "ID"),
            ("JISC", "University of Whacko", "X_12345"),
            (),     # Empty row
            ("JISC", "Hello World", "X_6789"),
            ("CORE", "University of No ID")
        ]
        with self.assertRaises(ValueError) as exc:
            num_loaded = Identifier.reload_type_by_identifier_iterable(iterator, "JISC")
        assert "Did not find any expected data in file: Instituion name, Numeric ID and, optionally, identifier type ('SWORD' or 'JISC')" == str(exc.exception)


        # Simulate CSV file with 2 columns: Type, Name, Id - BUT NO valid numeric ID
        iterator = [
            ("Filename row"),
            (),     # Empty row
            ("Name", "ID"),
            ("University of Whacko", "X_12345"),
            ("Hello World", "X_6789"),
            ("University of No ID")
        ]
        with self.assertRaises(ValueError) as exc:
            num_loaded = Identifier.reload_type_by_identifier_iterable(iterator, "JISC")
        assert "Did not find any expected data in file: Instituion name, Numeric ID and, optionally, identifier type ('SWORD' or 'JISC')" == str(exc.exception)


        # Simulate CSV file with 2 columns: Type, Name, Id - BUT missing a name
        iterator = [
            ("Filename row"),
            ("Name", "ID"),
            ("University of Whacko", "12345"),
            ("9999")
        ]
        with self.assertRaises(ValueError) as exc:
            num_loaded = Identifier.reload_type_by_identifier_iterable(iterator, "JISC")
        assert "Got only 1 element in the row" in str(exc.exception)


    @app_decorator
    def test_identifier_csv_list(self):
        first = IdentifierFactory.make_jisc("A")
        second = IdentifierFactory.make_jisc("B")
        third = IdentifierFactory.make_core("A")
        fourth = IdentifierFactory.make_core("B")

        csv_list = Identifier.identifiers_to_csv_list()[1:]  # Don't need header row

        assert len(csv_list) == 4

        assert csv_list[0] == ["JISC", "A", first.value]
        assert csv_list[1] == ["JISC", "B", second.value]
        assert csv_list[2] == ["CORE", "A", third.value]
        assert csv_list[3] == ["CORE", "B", fourth.value]

    @app_decorator
    def test_emails_in_affilations(self):
        """
        Create author objects with a common email inside the affiliations and assume that this common email
        will not appear in their identifiers
        """
        urn = note_models.UnroutedNotification()
        common_email_list = ["common@email.com"]
        auth_contrib = {
                # Dummy data for - not used
                "type" : "author",
                "organisation_name" : "Some Org",
                "identifier" : []
            }

        ### Initial test - ensure that ALL authors and contributors have the unique supplied email added as an Identifier,
        #   but NOT the common email.

        urn.authors = [
            self.create_author_with_emails_in_aff("Noddy Holder", auth_contrib, common_email_list + ["Noddy.Holder@email.com"]),
            self.create_author_with_emails_in_aff("John Smith", auth_contrib, common_email_list + ["john_smith@email.com"]),
            self.create_author_with_emails_in_aff("Jane Doe", auth_contrib, common_email_list + ["jane.doe@email.com"])
        ]
        urn.contributors = [
            self.create_author_with_emails_in_aff("Amy Contrib", auth_contrib, common_email_list + ["amy.contrib@email.com"]),
            self.create_author_with_emails_in_aff("Sam Smith", auth_contrib, common_email_list + ["Sam.Smith@email.com"])
        ]

        urn.add_affiliation_email_identifiers()

        assert set(author["identifier"][0]["id"] for author in urn.authors) == {
            "noddy.holder@email.com",
            "john_smith@email.com",
            "jane.doe@email.com"
        }
        assert set(contrib["identifier"][0]["id"] for contrib in urn.contributors) == {
            "amy.contrib@email.com",
            "sam.smith@email.com"
        }

        ### Confirm that if an email ID already exists the affiliation will NOT be searched for emails
        #   Ensure that email added only where there is NO existing email identifier
        urn.authors = [
            self.create_author_with_emails_in_aff("Existing Email-ident", auth_contrib, common_email_list + ["existing.email-ident@email.com"], "email_ident@test.com"),
        ]
        urn.contributors = [
            self.create_author_with_emails_in_aff("No Email-ident", auth_contrib, common_email_list + ["No.Email-ident@email.com"]),
        ]

        urn.add_affiliation_email_identifiers()

        # Author should have only the original email ident
        auth_id_list = urn.authors[0]["identifier"]
        assert len(auth_id_list) == 1
        assert auth_id_list[0] == {"type": "email", "id": "email_ident@test.com"}

        # Contrib should have new email ident (but NOT the common one)
        contrib_id_list = urn.contributors[0]["identifier"]
        assert len(contrib_id_list) == 1
        assert contrib_id_list[0] == {"type": "email", "id": "no.email-ident@email.com"}

        ### Confirm that duplicate emails are ignored in a case-insensitive way
        urn.authors = [
            self.create_author_with_emails_in_aff("Same Emails", auth_contrib, ["common@comm.co.uk", "same.emails@email.com", "Same.Emails@email.com", "SAME.EMAILS@EMAIL.COM"]),
        ]
        urn.contributors = [
            self.create_author_with_emails_in_aff("Two Emails", auth_contrib, ["COMMON@COMM.CO.UK", "one.email@email.com", "TWO.EMAIL@EMAIL.com"]),
        ]

        urn.add_affiliation_email_identifiers()

        # Author should have only ONE new email identifier (not the common one)
        auth_id_list = urn.authors[0]["identifier"]
        assert len(auth_id_list) == 1
        assert auth_id_list[0] == {"type": "email", "id": "same.emails@email.com"}

        # Contrib should have 2 new email idents (but NOT the common one)
        contrib_id_list = urn.contributors[0]["identifier"]
        assert len(contrib_id_list) == 2
        contrib_id_emails = [id_dict["id"] for id_dict in contrib_id_list]
        assert sorted(contrib_id_emails) == sorted(["one.email@email.com", "two.email@email.com"])


        ### Confirm that duplicate emails are recognised and ignored even where an auth or contrib already has an email ID
        urn.authors = [
            self.create_author_with_emails_in_aff("Existing Ident", auth_contrib, ["common@comm.co.uk"], "existing.ident@email.com"),
        ]
        urn.contributors = [
            self.create_author_with_emails_in_aff("Two Emails", auth_contrib, ["COMMON@COMM.CO.UK"]),
        ]

        urn.add_affiliation_email_identifiers()

        # Author should have only original existing email identifier (not the common one)
        auth_id_list = urn.authors[0]["identifier"]
        assert len(auth_id_list) == 1
        assert auth_id_list[0] == {"type": "email", "id": "existing.ident@email.com"}

        # Contrib should have NO email ident
        contrib_id_list = urn.contributors[0]["identifier"]
        assert len(contrib_id_list) == 0


    @app_decorator
    def test_setting_article_abstract(self):
        """
        Confirm that any prefix like "Abstract: " is stripped when abstract is set
        """
        urn = note_models.UnroutedNotification()

        abstracts_unchanged = ["The cat sat on the mat", "An abstract: is unchanged", "", "Abstraction is unchanged"]
        for a in abstracts_unchanged:
            urn.article_abstract = a
            routed_note = urn.make_routed()
            # Confirm no change was made to abstract string when it is saved
            assert routed_note.article_abstract == a

        abstracts_variants = ["Abstract", "ABSTRACT"]
        suffixes = [" ", ":  ", ":", ". ", ", "]
        for a in abstracts_variants:
            for s in suffixes:
                urn.article_abstract = a + s + "The cat sat on the mat"
                routed_note = urn.make_routed()
                # Confirm that "Abstract: " prefix is stripped (together with any immediately following punctuation/whitespace)
                assert routed_note.article_abstract == "The cat sat on the mat"

    @app_decorator
    def test_setting_article_acknowledgement(self):
        """
        Confirm that any prefix like "Acknowledgement: " is stripped when ack is set
        """
        urn = note_models.UnroutedNotification()
        urn.article_title = "X"
        ack_unchanged = ["The cat sat on the mat", "An acknowledgement: is unchanged", "", "Acknowledge is unchanged"]
        for a in ack_unchanged:
            urn.ack = a
            routed_note = urn.make_routed()
            # Confirm no change was made to ack string when it is saved
            assert routed_note.ack == a

        ack_varients = ["Acknowledgement",
                        "ACKNOWLEDGEMENTS",
                        "Acknowledgments",
                        "ACKNOWLEDGMENT"
                        ]
        suffixes = [" ", ":  ", ":", ". ", ", "]
        for a in ack_varients:
            for s in suffixes:
                urn.ack = a + s + "The cat sat on the mat"
                routed_note = urn.make_routed()
                # Confirm that "ACKNOWLEDG(E)MENT(S)" prefix is stripped (together with any immediately following punctuation/whitespace)
                assert routed_note.ack == "The cat sat on the mat"

    @app_decorator
    def test_cms(self):
        ctl_recs = []
        html_recs = {}
        ####
        # Create Test Data: 3 ctl records, and for each of those, create 4 HTML recs
        ####
        for cms_type, sort_by, multi, field_names in [
            ("type-one", "1", True, ["t1-one", "t1-two"]),
            ("type-two", "3", True, ["t2-one"]),
            ("type-three", "2", False, ["t3-one"])
        ]:
            ctl_recs.append(CMSFactory.make_ctl_record(cms_type, sort_by, multi, field_names))
            html_recs[cms_type] = []
            for status, sort in [("N", "d"), ("S", "c"), ("L", "b"), ("D", "a")]:
                html_recs[cms_type].append(CMSFactory.make_html_record(cms_type, status, sort, field_names))

        ####
        # Confirm that content types are listed as expected
        ####
        cms_types = CmsMgtCtl.list_cms_types()
        assert len(cms_types) == 3
        assert  cms_types == sorted([(r["cms_type"], r["brief_desc"]) for r in ctl_recs])

        ####
        # Confirm that HTML recs are listed as expected - All statuses for cms_type "type-one"
        ####
        for status, expected in [
            ("NL", 2),
            ("N", 1),
            ("L", 1),
            ("D", 1),
            ("S", 1),
            ("", 0),
            ("NLSD", 4),
        ]:
            html_recs_with_status = CmsHtml.list_content_of_type("type-one", status=status)
            assert len(html_recs_with_status) == expected

        # For last set of records retrieved (all recs of "type-one") we expect them to be retrieved in sort order
        # although they were inserted into database in order "d", "c", "b", "a"
        expected_sort_order = ["a", "b", "c", "d"]
        prev_id = None
        for ix, rec in enumerate(html_recs_with_status):
            assert rec["fields"]["sort_value"] == expected_sort_order[ix]
            if prev_id:
                assert rec["id"] < prev_id  # Confirm that records are listed in decreasing ID order
            prev_id = rec["id"]

        ##
        # Confirm that no recs are returned for unknown content type
        ##
        html_recs_type_unknown = CmsHtml.list_content_of_type("unknown", status="N")
        assert len(html_recs_type_unknown) == 0

        ####
        # Confirm set status works
        ####
        for ctype, rec_offset, status, expected in [
            ("type-one", 0, "N", "made new"),
            ("type-one", 0, "D", "deleted"),
            ("type-one", 0, "S", "superseded"),
            ("type-one", 0, "L", "made live"),
            ("type-one", 1, "D", "deleted"),    # Orig set to Superseded
        ]:
            set_status_dict= {
                "cms_type": ctype,
                "id": html_recs[ctype][rec_offset]["id"],
                "status": status
            }
            result_str = CmsHtml.update_status(set_status_dict)
            assert result_str == expected
        # Confirm that =number of records listed reflects new statuses for "type-one" content
        for status, expected in [
            ("L", 2),
            ("N", 0),
            ("S", 0),
            ("D", 2),
            ("NLSD", 4),
        ]:
            html_recs_with_status = CmsHtml.list_content_of_type("type-one", status=status)
            assert len(html_recs_with_status) == expected

        ####
        # Confirm save & archive content works - using "type-two", initially "Live" record
        ####
        type_2_live = html_recs["type-two"][2]  # We expect this was the 3rd rec inserted during Create Test Data step
        assert type_2_live["status"] == "L"
        rec_id = type_2_live["id"]
        edited_rec = deepcopy(type_2_live)

        ##
        # Just change sort_value - we expect record to be simply updated
        ##
        edited_rec["fields"]["sort_value"] = "x"
        result_str = CmsHtml.save_and_archive_content(edited_rec)
        assert result_str == "updated"
        # We now expect this record to be listed last
        html_recs_with_status = CmsHtml.list_content_of_type("type-two", status="NSLD")
        assert len(html_recs_with_status) == 4
        assert html_recs_with_status[-1]["id"] == rec_id

        ##
        # Now change the data value for field "t2-one" - we expect original record to be marked as superseded and new record created (still with Live status)
        ##
        edited_rec["fields"]["sort_value"] = "z"
        edited_rec["fields"]["t2-one"] = "Changed data field"
        result_str = CmsHtml.save_and_archive_content(edited_rec)
        assert result_str == "saved (& previous version archived)"
        # We now expect the new record to be listed last because of 'z' sort value
        html_recs_with_status = CmsHtml.list_content_of_type("type-two", status="NSLD")
        assert len(html_recs_with_status) == 5
        last_rec = html_recs_with_status[-1]
        assert last_rec["fields"]["sort_value"] == "z"
        assert last_rec["status"] == "L"
        assert last_rec["id"] > rec_id  # New record should have ID greater than original rec

        # Now check the original record has Superseded status (with values unchanged)
        orig_rec = CmsHtml.pull(rec_id, wrap=False)
        assert orig_rec["status"] == "S"    # Now marked as superseded (was previously "L")
        assert orig_rec["fields"]["sort_value"] == "x"
        assert orig_rec["fields"]["t2-one"] == type_2_live["fields"]["t2-one"]

    @app_decorator
    def test_ac_user_pull_functions(self):
        """

        :return:
        """
        # Each org account creates 4 users, 3 with db records, 1 of each type: Admin, Standard, Readonly.
        # Org accounts are OFF by default
        pub_live_org, pl_admin_user, pl_api_user_no_rec, pl_std_user, pl_ro_user = AccountFactory.publisher_account(org_only=False)
        pub_test_org, pt_admin_user, pt_api_user_no_rec, pt_std_user, pt_ro_user = AccountFactory.publisher_account(live=False, org_only=False)

        ##
        #   Test pull_all_user_n_org_accounts(...) function
        ##

        # Select all user accounts belonging to ON Orgs
        user_acs = AccUser.pull_all_user_n_org_accounts(org_types="RP", live_test="LT", role_codes="SRAJD", del_on_off="O", list_func=None)
        assert len(user_acs) == 0   # Both org accs are OFF

        # Select all user accounts belonging to OFF Orgs
        user_acs = AccUser.pull_all_user_n_org_accounts(org_types="RP", live_test="LT", role_codes="SRAJD", del_on_off="F", list_func=None)
        assert len(user_acs) == 6   # Both org accs, each with 3 users are OFF

        # Select all user accounts belonging to OFF Repository Orgs (of which there are NONE)
        user_acs = AccUser.pull_all_user_n_org_accounts(org_types="R", live_test="LT", role_codes="SRAJD", del_on_off="F", list_func=None)
        assert len(user_acs) == 0   # Both Publisher org accs, each with 3 users are OFF; there are NO Repo acs

        # Select only publisher Admin users
        user_acs = AccUser.pull_all_user_n_org_accounts(org_types="P", live_test="LT", role_codes="A", del_on_off="F", list_func=None)
        assert len(user_acs) == 2   # Each publisher has an Admin user
        for user in user_acs:
            assert user.role_code == "A"
            assert user.is_admin

        # Select only publisher Admin users for Test publisher acs
        user_acs = AccUser.pull_all_user_n_org_accounts(org_types="P", live_test="T", role_codes="A", del_on_off="F", list_func=None)
        assert len(user_acs) == 1   # 1 Test publisher
        assert user_acs[0] == pt_admin_user

        # Select only publisher Standard & Readonly users for Live & Test publisher acs
        user_acs = AccUser.pull_all_user_n_org_accounts(org_types="P", live_test="LT", role_codes="SR", del_on_off="F", list_func=None)
        assert len(user_acs) == 4   # Each publisher has 1 standard & 1 read-only user
        for user in user_acs:
            assert user.role_code in ["S", "R"]

        # Make Standard User DELETED
        pl_std_user.deleted_date = now_str()
        pl_std_user.update()
        # Select only DELETED users
        user_acs = AccUser.pull_all_user_n_org_accounts(org_types="P", live_test="LT", role_codes="SRA", del_on_off="D", list_func=None)
        assert len(user_acs) == 1
        assert user_acs[0] == pl_std_user

        # Test `list_func`
        def _list_func_ret_dict(user):
            return dict(ID=user.id, ROLE=user.role_code, IS_DELETED=user.deleted_date is not None)

        # Select DELETED users with `list_func`
        user_acs = AccUser.pull_all_user_n_org_accounts(org_types="P", live_test="LT", role_codes="SRA", del_on_off="D", list_func=_list_func_ret_dict)
        assert isinstance(user_acs[0], dict)
        assert user_acs[0] == {"ID": pl_std_user.id, "ROLE": "S", "IS_DELETED": True}

        ##
        #   Test pull_user_acs(...) function
        ##

        # Test for the Live publisher ac, get all users (including deleted), sorting by ID ascending
        user_acs = AccUser.pull_user_acs(pub_live_org.id, role_codes="SRA", inc_deleted=True, order_by="id ASC")
        assert len(user_acs) == 3
        assert user_acs[0].id < user_acs[1].id < user_acs[2].id

        # Test for the Live publisher ac, get all users (including deleted), sorting by ID Descending
        user_acs = AccUser.pull_user_acs(pub_live_org.id, role_codes="SRA", inc_deleted=True, order_by="id DESC")
        assert len(user_acs) == 3
        assert user_acs[0].id > user_acs[1].id > user_acs[2].id

        # Test for the Live publisher ac, get all users (EXCLUDING deleted)
        user_acs = AccUser.pull_user_acs(pub_live_org.id, role_codes="SRA", inc_deleted=False, order_by=None)
        assert len(user_acs) == 2

        # Test for the Live publisher ac, get READ-ONLY user
        user_acs = AccUser.pull_user_acs(pub_live_org.id, role_codes="R", inc_deleted=True, order_by=None)
        assert len(user_acs) == 1
        assert user_acs[0] == pl_ro_user

        ##
        #   Test pull_by_username(...) function
        ##

        # Attempt with DELETED user
        user_ac = AccUser.pull_by_username(pl_std_user.username)
        assert user_ac is None

        # Attempt with undeleted user
        user_ac = AccUser.pull_by_username(pt_ro_user.username)
        assert user_ac == pt_ro_user
        assert user_ac.acc_org is None

        ##
        #   Test pull_user_n_org_ac(...) function
        ##

        # Pull by username
        user_ac = AccUser.pull_user_n_org_ac(pt_admin_user.username, "username")
        assert user_ac == pt_admin_user
        assert user_ac.acc_org == pub_test_org

        # Pull by user_id
        user_ac = AccUser.pull_user_n_org_ac(pl_admin_user.id, "user_id")
        assert user_ac == pl_admin_user
        assert user_ac.acc_org == pub_live_org

        # Pull by user_uuid
        user_ac = AccUser.pull_user_n_org_ac(pl_ro_user.uuid, "user_uuid")
        assert user_ac == pl_ro_user
        assert user_ac.acc_org == pub_live_org

        ##
        #   Test pull_user_emails_roles_org_ids_by_role_n_org_type(...) function
        ##

        # Return a dict for Repository accounts (NONE are present)
        ret_dict = AccUser.pull_user_emails_roles_org_ids_by_role_n_org_type("R",
                                                                             role_codes="SRA",
                                                                             role_desc=True,
                                                                             return_dict=True)
        assert ret_dict == {}

        # Return a lisdt for Repository accounts (NONE are present)
        ret_list = AccUser.pull_user_emails_roles_org_ids_by_role_n_org_type("R",
                                                                             role_codes="SRA",
                                                                             role_desc=True,
                                                                             return_dict=False)
        assert ret_list == []

        # Return a dict for Publisher & Repository (none present) accounts, using role descriptions
        ret_dict = AccUser.pull_user_emails_roles_org_ids_by_role_n_org_type("PR",
                                                                             role_codes="SRA",
                                                                             role_desc=True,
                                                                             return_dict=True)
        assert isinstance(ret_dict, dict)
        assert ret_dict[pub_live_org.id] == {"Org admin": [pl_admin_user.username], "Read-only": [pl_ro_user.username]}
        assert ret_dict[pub_test_org.id] == {"Org admin": [pt_admin_user.username], "Read-only": [pt_ro_user.username], "Standard": [pt_std_user.username]}


        # Return a list for Publisher accounts, using role codes
        ret_list = AccUser.pull_user_emails_roles_org_ids_by_role_n_org_type("P",
                                                                             role_codes="SRA",
                                                                             role_desc=False,
                                                                             return_dict=False)
        assert ret_list == [
            (pub_live_org.id, 'A', pl_admin_user.username),
            (pub_live_org.id, 'R', pl_ro_user.username),
            (pub_test_org.id, 'A', pt_admin_user.username),
            (pub_test_org.id, 'R', pt_ro_user.username),
            (pub_test_org.id, 'S', pt_std_user.username),
        ]

        ##
        #   Test pull_user_email_details_by_org_id_n_role(...) function
        ##

        # Test for the Test publisher ac, get all users (EXCLUDING deleted), return List of Dicts containing Role-DESCRIPTION
        list_of_dicts = AccUser.pull_user_email_details_by_org_id_n_role(pub_test_org.id, role_codes="SRA", order_ind="role", role_desc=True, return_dict=False)
        assert len(list_of_dicts) == 3
        assert list_of_dicts == [
            {"email": pt_admin_user.user_email, "name": pt_admin_user.forename + " " + pt_admin_user.surname, "org_role":pt_admin_user.org_role, "role": pt_admin_user.role_short_desc},
            {"email": pt_ro_user.user_email, "name": pt_ro_user.forename + " " + pt_ro_user.surname, "org_role":pt_ro_user.org_role, "role": pt_ro_user.role_short_desc},
            {"email": pt_std_user.user_email, "name": pt_std_user.forename + " " + pt_std_user.surname, "org_role":pt_std_user.org_role, "role": pt_std_user.role_short_desc},
        ]
        # Test for the Live publisher ac, get READ-ONLY user, return List of Dicts containing Role-CODE
        list_of_dicts = AccUser.pull_user_email_details_by_org_id_n_role(pub_test_org.id, role_codes="R", order_ind="role", role_desc=False, return_dict=False)
        assert len(list_of_dicts) == 1
        assert list_of_dicts == [
            {"email": pt_ro_user.user_email, "name": pt_ro_user.forename + " " + pt_ro_user.surname, "org_role":pt_ro_user.org_role, "role": pt_ro_user.role_code},
        ]

        # Test for the Test publisher ac, get all users (EXCLUDING deleted), return Dict of Lists of Dicts containing Role-DESCRIPTION
        dict_of_list_of_dicts = AccUser.pull_user_email_details_by_org_id_n_role(pub_test_org.id, role_codes="SRA", order_ind="role", role_desc=True, return_dict=True)
        assert dict_of_list_of_dicts == {
            pt_admin_user.role_short_desc: [
                {"email": pt_admin_user.user_email, "name": pt_admin_user.forename + " " + pt_admin_user.surname, "org_role":pt_admin_user.org_role}
            ],
            pt_ro_user.role_short_desc: [
                {"email": pt_ro_user.user_email, "name": pt_ro_user.forename + " " + pt_ro_user.surname, "org_role":pt_ro_user.org_role}
            ],
            pt_std_user.role_short_desc: [
                {"email": pt_std_user.user_email, "name": pt_std_user.forename + " " + pt_std_user.surname, "org_role":pt_std_user.org_role}
            ]
        }
        # Test for the Live publisher ac, get READ-ONLY & STD user, return List of Dicts containing Role-CODE
        dict_of_list_of_dicts = AccUser.pull_user_email_details_by_org_id_n_role(pub_test_org.id, role_codes="RS", order_ind="role", role_desc=False, return_dict=True)
        assert dict_of_list_of_dicts == {
            "R": [
                {"email": pt_ro_user.user_email, "name": pt_ro_user.forename + " " + pt_ro_user.surname, "org_role": pt_ro_user.org_role}
            ],
            "S": [
                {"email": pt_std_user.user_email, "name": pt_std_user.forename + " " + pt_std_user.surname, "org_role":pt_std_user.org_role}
            ]
        }
