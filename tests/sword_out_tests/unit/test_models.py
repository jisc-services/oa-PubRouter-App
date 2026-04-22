"""
Tests on the models
"""
from octopus.lib import dataobj, dates

from router.shared.models.account import AccOrg
from router.shared.models.sword_out import SwordDepositRecord, DEPOSITED, FAILED
from router.jper_sword_out.app import app_decorator, app
from tests.fixtures.factory import AccountFactory, SwordFactory
from tests.fixtures.testcase import JPERMySQLTestCase


class TestModels(JPERMySQLTestCase):

    @classmethod
    @app_decorator
    def setUpClass(cls):
        # List the tables (by table name) needed for testing
        cls.tables_for_testing = ['account', 'acc_user', 'sword_deposit']

        super(TestModels, cls).setUpClass()
        app.config["LOGFILE"] = "/tmp/sword-out-tests.log"

    @app_decorator
    def setUp(self):
        super(TestModels, self).setUp()

    @app_decorator
    def tearDown(self):
        super(TestModels, self).tearDown()

    @app_decorator
    def test_01_account(self):
        # first load some accounts into the system, some with and some without sword support
        acc1 = AccountFactory.repo_account(sword_username_pwd_collection_list=["acc1", "pass1", "http://sword/1"])
        acc2 = AccountFactory.repo_account(sword_username_pwd_collection_list=["acc2", "pass2", "http://sword/2"])
        acc3 = AccountFactory.repo_account(sword_username_pwd_collection_list=[None, None, None])
        acc4 = AccountFactory.repo_account(sword_username_pwd_collection_list=[None, None, None])

        accs = AccOrg.with_sword_activated()
        assert len(accs) == 2
        for acc in accs:
            assert acc.repository_data.sword_collection in ("http://sword/1", "http://sword/2")

    @app_decorator
    def test_03_deposit_record(self):
        # make a blank one
        dr = SwordDepositRecord

        # test all its methods
        dataobj.test_dataobj(dr, SwordFactory.deposit_record())

        # make a new one around some existing data
        dr = SwordDepositRecord(SwordFactory.deposit_record())

        # check the was_successful calculations
        # when the metadata fails, that is a certain failure irrespective of the other values
        dr.metadata_status = FAILED
        dr.content_status = DEPOSITED
        dr.completed_status = DEPOSITED
        assert not dr.was_successful()

        # across the board success
        dr.metadata_status = DEPOSITED
        dr.content_status = DEPOSITED
        dr.completed_status = DEPOSITED
        assert dr.was_successful()

        # failed at the complete stage
        dr.metadata_status = DEPOSITED
        dr.content_status = DEPOSITED
        dr.completed_status = FAILED
        assert dr.was_successful()

        # failed at the content stage
        dr.metadata_status = DEPOSITED
        dr.content_status = FAILED
        dr.completed_status = DEPOSITED
        assert dr.was_successful()

        # successful metadata-only deposit
        dr.metadata_status = DEPOSITED
        dr.content_status = None
        dr.completed_status = None
        assert dr.was_successful()

    @app_decorator
    def test_04_deposit_record_pull(self):
        dd = dates.now_str()

        # create a deposit record with some properties we can check
        dr = SwordDepositRecord()
        dr.notification = 123
        dr.repository = 456
        dr.metadata_status = DEPOSITED
        dr.content_status = DEPOSITED
        dr.completed_status = FAILED
        dr.insert()

        # first check an empty response
        r = SwordDepositRecord.pull_most_recent_by_note_id_and_repo_id(123, 999)
        assert r is None

        # now check we can retrieve the real thing
        r = SwordDepositRecord.pull_most_recent_by_note_id_and_repo_id(123, 456)
        assert r.notification == 123
        assert r.repository == 456
        assert r.metadata_status == DEPOSITED
        assert r.content_status == DEPOSITED
        assert r.completed_status == FAILED
