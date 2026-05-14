"""
Unit tests for DeDuplication
"""
from tests.fixtures.factory import AccountFactory, NotificationFactory
from router.jper.app import app_decorator
import router.shared.models.doi_register as doi_reg
from tests.fixtures.testcase import JPERMySQLTestCase


class TestDedup(JPERMySQLTestCase):

    @classmethod
    @app_decorator
    def setUpClass(cls):
        # List the tables (by table name) needed for testing
        cls.tables_for_testing = ['account', 'acc_user']
        super(TestDedup, cls).setUpClass()


    @app_decorator
    def setUp(self):
        # need to do this first, before kicking upstairs, as ESTestCase runs initialise
        super(TestDedup, self).setUp()
        self.maxDiff = None     # Provides more info if some assertions fail


    @app_decorator
    def tearDown(self):
        super(TestDedup, self).tearDown()

    @staticmethod
    def create_pub_acc():
        """
        Create publisher account.
        :return: publisher account object
        """
        publisher = AccountFactory.publisher_account()
        # Set the publisher to be active
        publisher.status = 1
        publisher.update()
        # self.publisher_api_key = publisher.api_key
        return publisher

    @staticmethod
    def create_repo_acc(live=True, org_name="Repository account", dup_setting=None):
        """
        Create repository account
        :param live:  Boolean - True: Live account;  False: Test account
        :param org_name: String  - Account org-name (if None then default will apply)
        :param dup_setting: String - duplication setting
        :return: repo account object
        """
        repo_acc = AccountFactory.repo_account(live=True) if live else AccountFactory.repo_account(live=False)
        repo_acc.org_name = "{} ({})".format(org_name, "live" if live else "test")
        repo_acc.update()
        return repo_acc

    @app_decorator
    def test_01_metric_calculations(self):
        """
        Check that notification bit_fields and related metrics and their differences are correctly calculated.
        """
        created_date = "2021-02-22T10:03:05Z"
        note_dict = NotificationFactory.unrouted_notification(no_id_or_created=True)
        note_dict["id"] = "test_id_1_1234567890"
        note_dict["created"] = created_date
        del (note_dict["metadata"]["license_ref"])
        del (note_dict["metadata"]["article"]["num_pages"])
        del (note_dict["metadata"]["article"]["e_num"])
        del (note_dict["metadata"]["accepted_date"])
        del (note_dict["metadata"]["funding"][0]["grant_numbers"])
        del (note_dict["metadata"]["funding"][1])
        del (note_dict["metadata"]["author"][0]["identifier"])
        orig_metrics = doi_reg.calc_notification_metrics(note_dict)
        self.assertDictEqual(orig_metrics,
                             {'n_auth': 2,
                              'n_orcid': 1,
                              'n_fund': 1,
                              'n_fund_id': 2,
                              'n_grant': 0,
                              'n_lic': 0,
                              'n_struct_aff': 1,
                              'n_aff_ids': 1,
                              'n_cont': 1,
                              'n_hist': 1,
                              'm_date': created_date,
                              'bit_field': 14945143726078})

        # Sort by Bit number
        set_on, set_off = doi_reg.describe_bit_settings(orig_metrics['bit_field'], True, 0)
        assert len(set_on) == 34
        assert len(set_off) == 9
        expected_off = [
            # [Bit number, Description, Rating]
            [13, 'Article version - VoR', 1],
            [14, 'Article version - EVoR or CVoR', 0],
            [18, 'Article number of pages', 2],
            [28, 'Accepted date', 1],
            [30, 'Publication date (partial)', 1],
            [35, 'Grant numbers', 1],
            [37, 'Open licence', 1],
            [38, 'Other licence', 1],
            [41, 'Electronic article number', 2]
        ]
        assert set_off == expected_off

        created_date_2 = "2021-03-11T06:22:10Z"
        note_dict_2 = NotificationFactory.unrouted_notification(no_id_or_created=True)
        note_dict_2["id"] = "test_id_2_1234567890"
        note_dict_2["created"] = created_date_2
        del (note_dict_2["metadata"]["journal"]["abbrev_title"])
        del (note_dict_2["metadata"]["contributor"])
        note_dict_2["metadata"]["funding"].append({"name": "TEST", "grant_numbers": ["Test/111", "Test/222"]})
        # Add a structured affiliation entry to 2nd author (which initially has only a "raw" entry
        note_dict_2["metadata"]["author"][1]["affiliations"][0]["identifier"] = [{"type": "ISNI", "id": "isni 8888 7777 6666"}]
        metrics_2 = doi_reg.calc_notification_metrics(note_dict_2)
        self.assertDictEqual(metrics_2,
                             {
                                 'n_auth': 2,
                                 'n_orcid': 2,
                                 'n_fund': 3,
                                 'n_fund_id': 5,
                                 'n_grant': 4,
                                 'n_lic': 3,
                                 'n_struct_aff': 2,
                                 'n_aff_ids': 2,
                                 'n_cont': 0,
                                 'n_hist': 1,
                                 'm_date': created_date_2,
                                 'bit_field': 17590978060270
                            })

        set_on, set_off = doi_reg.describe_bit_settings(metrics_2['bit_field'], True, 0)
        assert len(set_on) == 38
        assert len(set_off) == 5
        expected_off = [
            [4, 'Journal abbreviated title', 3],
            [13, 'Article version - VoR', 1],
            [14, 'Article version - EVoR or CVoR', 0],
            [27, 'Contributors', 3],
            [30, 'Publication date (partial)', 1],
        ]
        assert set_off == expected_off

        diff, new_bits, counts_changed = doi_reg.compare_metrics(orig_metrics, metrics_2)
        assert new_bits != 0
        assert counts_changed == 0  # Some increased, others decreased
        self.assertDictEqual(diff,
                             {
                                 'old_date': '2021-02-22T10:03:05Z',
                                 'old_bits': 14945143726078,
                                 'curr_bits': 17590978060270,
                                 'n_auth': 0,
                                 'n_orcid': 1,
                                 'n_fund': 2,
                                 'n_fund_id': 3,
                                 'n_grant': 4,
                                 'n_lic': 3,
                                 'n_struct_aff': 1,
                                 'n_aff_ids': 1,
                                 'n_cont': -1,
                                 'n_hist': 0,
                             })

        diff_dict = doi_reg.describe_differences(diff)
        diff_dict['new'].sort()
        diff_dict['increased'].sort()
        expected_dict = {
            'old_date': '2021-02-22T10:03:05Z',
            'new': [
                'Accepted date',
                'Article number of pages',
                'Electronic article number',
                'Grant numbers',
                'Open licence',
                'Other licence'
            ],
            'lost': [
                'Contributors',
                'Journal abbreviated title'
            ],
            'increased': [
                '1 more Author ORCID',
                '1 more Author with affiliation Org Id(s)',
                '1 more Author with structured affiliation(s)',
                '2 more Funders',
                '3 more Funder Identifiers',
                '3 more Licences',
                '4 more Grant numbers'
            ],
            'decreased': [
                '1 less Contributor'
            ],
            'add_bits': 15865944997888
        }
        # print("\nDIFF_DICT\n", diff_dict)
        self.assertDictEqual(diff_dict, expected_dict)
