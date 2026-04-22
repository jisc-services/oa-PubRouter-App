"""
X_test_deposit.py -
    While this filename does NOT start with "test_...." it will NOT be executed.  It has been removed from general
    execution while the repository servers have been made inaccessible from public internet for security reasons.
    Once the servers have been upgraded this file will be reinstated.
----------------------------------------------------------------------------------------------------------------------

Test the full range of deposit features of sword2 against a test repository, this test will run multiple times on
different repository types, using the parameterized library.

In order to successfully run this test you need a repository set up to receive the deposits via SWORDv2, and
you need to add respective repository configuration settings in this file.

If adding a test to this set which you wish to apply to the full set of repositories then ensure that you decorate
your function with @parameterized.expand(repo_list). This will cause the tests to be run multiple times using the
different repository configurations stated in test_deposit_config.ini and listed in repository_list.

The @parameterized.expand() decorator creates n tests given a set of n arguments to @parameterized.expand(),
replacing the arguments of the function decorated with the arguments given to @parameterized.expand(). So all functions
in this test suite take 'repo_name' as an argument, and @parameterized.expand() replaces this value with different
repository names and generates a new test function for each repository name given. For example, if we assume that
repository_list = ['dspace', 'eprints'] then our test_01_metadata_deposit_success gets turned into two separate test
functions test_01_metadata_deposit_success_dspace and test_01_metadata_deposit_success_eprints with repo_name input
as dspace and eprints respectively.
"""
import shutil
import os
from zipfile import ZipFile

from flask import current_app
from parameterized import parameterized

from router.shared.models.note import RoutedNotification
from router.shared.models.account import AccOrg, OKAY
from router.shared.models.sword_out import SwordDepositRecord, DEPOSITED, FAILED
from router.jper_sword_out.app import app_decorator
from router.jper_sword_out.deposit import Deposit, MetadataException, CompletionException, FileDepositException

from tests.fixtures.factory import AccountFactory
from tests.sword_out_tests.fixtures.notifications import NotificationFactory
from tests.sword_out_tests.fixtures.testcase import SwordOutTestCase

# list of current repositories this test set will test has to sit on this level of scope for parameterized to work
# the values correspond to the CONFIGURATIONS found below.
# repository_list = ['DSPACE', 'EPRINTS', 'DSPACE_RIOXX']
repository_list = ['EPRINTS', 'EPRINTS_RIOXX']   # Currently we don't have DSPACE servers

repo_config = {
    "EPRINTS": {
        # the packaging preference of the repository (this value is used as default)
        # this will also default to http://purl.org/net/sword/package/SimpleZip
        "packaging": "https://purl.org/net/sword/package/SimpleZip",
        # url of the respective repository
        "repository_url": "http://eprints.pubrouter.jisc.ac.uk/id/contents",
        # a broken url, used in a test which expects this configuration type to fail
        "broken_repository_url": "https://eprints.pubrouter.jisc.ac.uk/id/thisdoesntexist",
        # repository username
        "username": "jper_sword_out",
        # repository password
        "password":"Password1",
        # repository name
        "repository_name": "eprints",
        # repository xml format
        "xml_format":"eprints"
    },
    "EPRINTS_RIOXX": {
        # the packaging preference of the repository (this value is used as default)
        # this will also default to http://purl.org/net/sword/package/SimpleZip
        "packaging": "https://purl.org/net/sword/package/SimpleZip",
        # url of the respective repository
        "repository_url": "http://eprints-rioxx.pubrouter.jisc.ac.uk/id/contents",
        # a broken url, used in a test which expects this configuration type to fail
        "broken_repository_url": "https://eprints-rioxx.pubrouter.jisc.ac.uk/id/thisdoesntexist",
        # repository username
        "username": "jper_sword_out",
        # repository password
        "password":"Password1",
        # repository name
        "repository_name": "eprints-rioxx",
        # repository xml format
        "xml_format":"eprints-rioxx-2"
    },
    "DSPACE": {
        "packaging": "http://purl.org/net/sword/package/SimpleZip",
        "repository_url": "https://dspace.pubrouter.jisc.ac.uk/swordv2/collection/123456789/183",
        "broken_repository_url": "https://dspace.pubrouter.jisc.ac.uk/swordv2/collection/123456789/doesntexist",
        "username": "dspace-sword@jisc.ac.uk",
        "password": "kN1ght+ARM=0ur",
        "repository_name": "dspace",
        "xml_format":"dspace"
    },
    "DSPACE_RIOXX": {
        "packaging": "http://purl.org/net/sword/package/SimpleZip",
        "repository_url": "https://dspace-rioxx.pubrouter.jisc.ac.uk/swordv2/collection/123456789/2372",
        "broken_repository_url": "https://dspace-rioxx.pubrouter.jisc.ac.uk/swordv2/collection/123456789/ded",
        "username": "dspace-sword@jisc.ac.uk",
        "password": "kN1ght+ARM=0ur",
        "repository_name": "dspace-rioxx",
        "xml_format":"dspace-rioxx"
    }
}



def zip_mock_file_create(_id, filename):
    # Helper function which creates a zip to be used in testing.
    mock_file_folder = current_app.config["STORE_MAIN_DIR"] + "/" + str(_id)
    if not os.path.exists(mock_file_folder):
        os.makedirs(mock_file_folder)

    mock_file_path = mock_file_folder + "/" + filename
    with ZipFile(mock_file_path, 'w') as myzip:
        myzip.writestr(f"testdata_{_id}.txt", f"testdata-{_id} blah blah blah...")


def storage_mock_file_delete(_id):
    mock_file_folder = current_app.config["STORE_MAIN_DIR"] + "/" + str(_id)
    shutil.rmtree(mock_file_folder)


class TestDeposit(SwordOutTestCase):

    @classmethod
    @app_decorator
    def setUpClass(cls):
        # List the tables (by table name) needed for testing
        cls.tables_for_testing = ['account', 'acc_user', 'notification', 'notification_account', 'sword_deposit']

        super(TestDeposit, cls).setUpClass()

        # get our repository configurations for future use
        # self.repocfg will be a dict with keys corresponding to Repositories: see repository_list (defined above).
        cls.repocfg = repo_config
        current_app.config["STORE_TYPE"] = "local"
        cls.deposit = Deposit.init_cls()


    @app_decorator
    def setUp(self):
        super(TestDeposit, self).setUp()

    @app_decorator
    def tearDown(self):
        super(TestDeposit, self).tearDown()

    def create_base_test_account(self, repo_test_config, save=True, good_repo_url=True):
        """
        Set basic repository config values: SWORD credentials, repository-xml-format and packaging.

        :param repo_test_config: test configuration dict
        :param save: Boolean indicates whether to save new account or not
        :param good_repo_url: Boolean indicates whether to use good or bad repository_url
        :return: account object
        """
        sword_creds = [
            repo_test_config['username'],
            repo_test_config['password'],
            repo_test_config['repository_url'] if good_repo_url else repo_test_config['broken_repository_url']
        ]
        acc = AccountFactory.repo_account(sword_username_pwd_collection_list=sword_creds,
                                          repo_xml_format=repo_test_config['xml_format'],
                                          save=False)
        if save:
            acc.insert()
        return acc

    @parameterized.expand(repository_list)
    @app_decorator
    def test_01_metadata_content_complete_deposit_success(self, repo_name):
        """
        Test function which a metadata deposit with all the correct credentials behaves as expected (succeeds)
        :param repo_name: parameterized repository name: either 'dspace' or 'eprints' at time of writing
        """
        current_app.logger.debug("\n\n**** START test_01 for %s ****\n\n", repo_name)

        acc = self.create_base_test_account(self.repocfg[repo_name])
        repo_data = acc.repository_data
        note = NotificationFactory.routed_notification(acc.id, article_title=f"Test_01 Metadata Content & Complete OK [{repo_name}]")

        deposit_record = SwordDepositRecord()
        deposit_record.content_status = FAILED

        receipt = self.deposit.metadata_deposit(note, repo_data, deposit_record, complete=False)

        assert receipt is not None
        # check the properties of the deposit_record
        assert deposit_record.metadata_status == DEPOSITED

        path = NotificationFactory.example_package_path()
        note.links[2]['url'] = path
        with open(path, "rb") as f:
            self.deposit.package_deposit_file(note.links[2], receipt, f, repo_data, deposit_record)

        # check the properties of the deposit_record
        assert deposit_record.metadata_status == DEPOSITED
        assert deposit_record.content_status == DEPOSITED

        # finally issue the complete request
        self.deposit.complete_deposit(receipt, repo_data, deposit_record)
        assert deposit_record.completed_status == DEPOSITED


    @parameterized.expand(repository_list)
    @app_decorator
    def test_02_metadata_deposit_fail(self, repo_name):
        """
        Test that with incorrect configuration a metadata deposit behaves as expected (fails)
        :param repo_name: parameterized repository name: either 'dspace' or 'eprints' at time of writing
        """
        current_app.logger.debug("\n\n**** START test_02 for %s ****\n\n", repo_name)

        acc = self.create_base_test_account(self.repocfg[repo_name], good_repo_url=False)
        note = NotificationFactory.routed_notification(acc.id, article_title=f"Test_02 Metadata deposit fail [{repo_name}]")

        deposit_record = SwordDepositRecord()

        with self.assertRaises(MetadataException) as exc:
            self.deposit.metadata_deposit(note, acc.repository_data, deposit_record, complete=True)
        exception = exc.exception
        assert exception.xml_doc is not None
        assert exception.xml_format == acc.repository_data.repository_xml_format

        # check the properties of the deposit_record
        assert deposit_record.metadata_status == FAILED


    @parameterized.expand(repository_list)
    @app_decorator
    def test_03_content_deposit_fail(self, repo_name):
        """
        Check that behaviour upon a failed content deposit is as expected (fails)
        :param repo_name: parameterized repository name: either 'dspace' or 'eprints' at time of writing
        """
        current_app.logger.debug("\n\n**** START test_03 for %s ****\n\n", repo_name)

        # first a successful deposit of metadata
        acc = self.create_base_test_account(self.repocfg[repo_name])
        repo_data = acc.repository_data
        note = NotificationFactory.routed_notification(acc.id, article_title=f"Test_03 Content fail [{repo_name}]")
        deposit_record = SwordDepositRecord()
        deposit_record.content_status = FAILED

        receipt = self.deposit.metadata_deposit(note, repo_data, deposit_record, complete=False)

        # now mess with the receipt to generate a failure
        em = receipt.em_iri
        bits = em.split("/")
        bits[len(bits) - 1] = "randomobjectidentifier"
        links = receipt.links
        new_links = []
        for link in links:
            if link.rel == "edit-media":
                link.href = "/".join(bits)
            new_links.append(link)
        receipt.links = new_links

        path = NotificationFactory.example_package_path()
        note.links[2]['url'] = path
        with open(path, "rb") as f:
            try:
                result = self.deposit.package_deposit_file(note.links[2], receipt, f, repo_data, deposit_record)
                assert result is None
            except FileDepositException:
                pass

        # check the properties of the deposit_record
        assert deposit_record.metadata_status == DEPOSITED
        assert deposit_record.content_status == FAILED


    @parameterized.expand(repository_list)
    @app_decorator
    def test_04_complete_deposit_fail(self, repo_name):
        """
        Test that a failed complete deposit behaves in the manner expected (fails)
        :param repo_name: parameterized repository name: either 'dspace' or 'eprints' at time of writing
        """
        current_app.logger.debug("\n\n**** START test_04 for %s ****\n\n", repo_name)

        acc = self.create_base_test_account(self.repocfg[repo_name])
        repo_data = acc.repository_data
        note = NotificationFactory.routed_notification(acc.id, article_title=f"Test_04 Content OK & Complete Fail [{repo_name}]")

        deposit_record = SwordDepositRecord()

        receipt = self.deposit.metadata_deposit(note, repo_data, deposit_record, complete=False)

        # now do a successful content deposit
        path = NotificationFactory.example_package_path()
        note.links[2]['url'] = path
        with open(path, "rb") as f:
            self.deposit.package_deposit_file(note.links[2], receipt, f, repo_data, deposit_record)

        # now mess with the receipt to generate a failure
        em = receipt.se_iri
        if em is None:  # EPrints doesn't return an SE-IRI
            em = receipt.edit_iri
        bits = em.split("/")
        bits[len(bits) - 1] = "randomobjectidentifier"

        repo_is_eprints = acc.repository_data.is_eprints()
        # finally issue the complete request (if this is not an eprints repository)
        if repo_is_eprints:
            self.deposit.complete_deposit(receipt, repo_data, deposit_record)
        else:
            with self.assertRaises(CompletionException):
                links = receipt.links
                new_links = []
                for link in links:
                    if link.rel == "http://purl.org/net/sword/terms/add":
                        link.href = "/".join(bits)
                    new_links.append(link)
                receipt.links = new_links
                self.deposit.complete_deposit(receipt, repo_data, deposit_record)

        # check the properties of the deposit_record
        assert deposit_record.metadata_status == DEPOSITED
        assert deposit_record.content_status == DEPOSITED
        if repo_is_eprints:
            assert deposit_record.completed_status == DEPOSITED
        else:
            assert deposit_record.completed_status == FAILED


    @parameterized.expand(repository_list)
    @app_decorator
    def test_05_full_cycle_success(self, repo_name):
        """
        A full cycle, with correct credentials and flow, check that behaviour is as expected (succeeds)
        :param repo_name: parameterized repository name
        """
        current_app.logger.debug("\n\n**** START test_05 for %s ****\n\n", repo_name)
        repo_test_config = self.repocfg[repo_name]

        acc1 = self.create_base_test_account(repo_test_config, save=False)
        repo_data1 = acc1.repository_data
        repo_data1.last_deposited_note_id = 111
        repo_data1.status = OKAY
        repo_data1.insert()

        acc2 = self.create_base_test_account(repo_test_config)

        # Repository accounts WITHOUT sword details - excpect that no deposits attempted for this.
        acc3 = AccountFactory.repo_account(sword_username_pwd_collection_list=[None, None, None])


        # now make some notifications to be returned over http
        # defining this mock here for convenience during development
        def mock_iterator_obj(since_id=0, since_date=None, repo_id=None, **kwargs):

            class X:
                def __init__(self, since_id=0, since_date=None, repo_id=None):
                    self.note_list = []
                    self.article_title = f"Test_05 Full lifecycle [{repo_name}] Repo_{repo_id} Note_"
                    if since_id:
                        self.ids = since_id + 1
                    else:
                        self.ids = 200

                def __enter__(self):
                    self.note_list = NotificationFactory.routed_note_obj_list(
                        2, ids=self.ids, article_title=self.article_title)

                def __iter__(self):
                    return self

                def __next__(self):
                    if not self.note_list:
                        raise StopIteration

                    return self.note_list.pop(0)

                def __exit__(self, exc_type, exc_val, exc_tb):
                    pass

            return X(since_id, since_date, repo_id)

        # set up the mock files corresponding to Notifications with specified IDs
        ids = [112, 113, 200, 201]
        for _id in ids:
            zip_mock_file_create(_id, "ArticleFilesJATS.zip")

        save_iterate_notifications = RoutedNotification.routed_scroller_obj
        RoutedNotification.routed_scroller_obj = mock_iterator_obj

        # now run the full stack
        self.deposit.send_notes_to_sword_acs()
        
        RoutedNotification.routed_scroller_obj = save_iterate_notifications

        # delete the mock files
        for _id in ids:
            storage_mock_file_delete(_id)

        # now check over everything and make sure what we expected to happen happened
        test_dict = {
            acc1.id: [112, 113],
            acc2.id: [200, 201],
            acc3.id: []
        }

        for ac_id, ids in test_dict.items():
            # Confirm that there are successful repository status records
            acc = AccOrg.pull(ac_id)
            repo_data1 = acc.repository_data
            assert repo_data1.status == OKAY
            assert repo_data1.retries == 0
            assert repo_data1.last_tried is None
            if ids:
                assert repo_data1.last_deposit_date is not None
                assert repo_data1.last_deposited_note_id == ids[-1]
                # Confirm there are deposit records for each notification in each account context
                for id in ids:
                    dr = SwordDepositRecord.pull_most_recent_by_note_id_and_repo_id(id, ac_id)
                    assert dr is not None
                    assert dr.metadata_status == DEPOSITED
                    if not "eprints-rioxx" in repo_data1.repository_xml_format:
                        assert dr.content_status == DEPOSITED
                        assert dr.completed_status == DEPOSITED
                    assert dr.doi == "55.aa/base.1"
            else:
                assert repo_data1.last_deposit_date is None
                assert repo_data1.last_deposited_note_id is None

    @parameterized.expand(repository_list)
    @app_decorator
    def test_06_metadata_deposit_success_special_character(self, repo_name):
        """
        Check that a metadata_deposit with special characters behaves as expected (doesn't break, is successful)
        :param repo_name: parameterized repository name: either 'dspace' or 'eprints' at time of writing
        """
        current_app.logger.debug("\n\n**** START test_06 for %s ****\n\n", repo_name)
        note = NotificationFactory.special_character_notification(title_prefix = f"Test_06 Special char deposit OK [{repo_name}]: ")

        acc = self.create_base_test_account(self.repocfg[repo_name])

        deposit_record = SwordDepositRecord()

        receipt = self.deposit.metadata_deposit(note, acc.repository_data, deposit_record, complete=True)

        assert receipt is not None
        # check the properties of the deposit_record
        assert deposit_record.metadata_status == DEPOSITED

