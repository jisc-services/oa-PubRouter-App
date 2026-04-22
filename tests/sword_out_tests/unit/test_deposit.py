"""
Tests on the deposit functions
"""
import os
import datetime
from time import sleep
from flask import current_app
from unittest.mock import patch
from mysql.connector.errors import InterfaceError

from sword2.models import DepositReceipt
from sword2.client.util import SwordException
from octopus.lib import dates, http
from octopus.modules.mysql.dao import DAOException
from router.shared.models.note import RoutedNotification
from router.shared.models.account import AccOrg, OKAY, FAILING, PROBLEM
from router.shared.models.sword_out import SwordDepositRecord, DEPOSITED, FAILED
from router.jper_sword_out.app import app_decorator
from router.jper_sword_out.deposit import Deposit, DepositException, MetadataException, FileDepositException,\
    CompletionException, GetFileException
from tests.fixtures.factory import AccountFactory
from tests.sword_out_tests.fixtures.notifications import RESOURCES, NotificationFactory, MockNoteScroller
from tests.sword_out_tests.fixtures.testcase import SwordOutTestCase


def mock_process_account_fail(*args, **kwargs):
    raise DAOException("oops")


def mock_process_notification_fail(*args, **kwargs):
    err_msg = """SWORD EXCEPTION:
Request Headers: {'Content-Length': '5440', 'Accept': '*/*', 'Content-Type': 'application/vnd.eprints.data+xml; charset=utf-8', 'Accept-Encoding': 'gzip, deflate', 'Authorization': 'Basic cHVicm91dGVyQGNhcmRpZmYuYWMudWs6YzRSZCFmRnVOMQ==', 'User-Agent': 'python-requests/2.24.0', 'In-Progress': 'true', 'Connection': 'keep-alive'}
Response Status Code: 401
Response Content:
b'<!DOCTYPE HTML PUBLIC "-//IETF//DTD HTML 2.0//EN">
<html><head>
<title>401 Unauthorized</title>
</head><body>
<h1>Unauthorized</h1>
<p>This server could not verify that you
are authorized to access the document
requested.  Either you supplied the wrong
credentials (e.g., bad password), or your
browser doesn't understand how to supply
the credentials required.</p>
</body></html>
"""
    orig_exception = SwordException("ERROR: the server returned malformed xml or a webpage.")
    raise DepositException("ORG NAME", "AC_123456789", "NOTE_123456789", "Metadata", err_msg, orig_exception)


def mock_process_notification_success(*args, **kwargs):
    return True


def mock_metadata_deposit_fail(note, repo_data, deposit_record, complete=False, **kwargs):
    err_msg = """SWORD EXCEPTION:
Request Headers: {'Content-Length': '5440', 'Accept': '*/*', 'Content-Type': 'application/vnd.eprints.data+xml; charset=utf-8', 'Accept-Encoding': 'gzip, deflate', 'Authorization': 'Basic cHVicm91dGVyQGNhcmRpZmYuYWMudWs6YzRSZCFmRnVOMQ==', 'User-Agent': 'python-requests/2.24.0', 'In-Progress': 'true', 'Connection': 'keep-alive'}
Response Status Code: 401
Response Content:
b'<!DOCTYPE HTML PUBLIC "-//IETF//DTD HTML 2.0//EN">\n<html><head>\n<title>401 Unauthorized</title>\n</head><body>\n<h1>Unauthorized</h1>\n<p>This server could not verify that you\nare authorized to access the document\nrequested.  Either you supplied the wrong\ncredentials (e.g., bad password), or your\nbrowser doesn\'t understand how to supply\nthe credentials required.</p>\n</body></html>\n
"""
    sword_exception = SwordException('ERROR: the server returned malformed xml or a webpage.')
    deposit_record.metadata_status = FAILED
    raise MetadataException(err_msg, sword_exception)


def mock_metadata_deposit_success(note, repo_data, deposit_record, complete=False, **kwargs):
    deposit_record.metadata_status = DEPOSITED

    return DepositReceipt()


def mock_package_deposit_file_fail(link, receipt, file_handle, repo_data, deposit_record, **kwargs):
    err_msg = "HTTPSConnectionPool(host='router.test.whiterose.ac.uk', port=443): Max retries exceeded with url: /id/eprint/87138/contents  (Caused by SSLError(SSLError(1, '[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed (_ssl.c:645)'),))"
    exception = Exception(
        """SSLError(MaxRetryError("HTTPSConnectionPool(host='router.test.whiterose.ac.uk', port=443): Max retries exceeded with url: /id/eprint/87138/contents (Caused by SSLError(SSLError(1, '[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed (_ssl.c:645)'),))",),)""")
    current_app.logger.info(f"Depositing Package file {file_handle.name} for Account:{repo_data.id}")
    deposit_record.content_status = FAILED
    raise FileDepositException(file_handle.name, "test_article.pdf", link.get("packaging"), err_msg, exception)


def mock_package_deposit_file_success(link, receipt, file_handle, repo_data, deposit_record, **kwargs):
    current_app.logger.info(f"Depositing Package file {file_handle.name} for Account:{repo_data.id}")
    deposit_record.content_status = DEPOSITED
    pass

def mock_process_link_package_deposit(link_file_dict, note, acc, repo_data, receipt, deposit_record, in_disk_store,
                                          reqd_content_type=None, **kwargs):
    current_app.logger.info(f"Process link_package_deposit for Account:{repo_data.id}")
    deposit_record.content_status = DEPOSITED
    pass


def mock_complete_deposit_fail(receipt, repo_data, deposit_record, **kwargs):
    err_msg = """b'<!DOCTYPE HTML PUBLIC "-//IETF//DTD HTML 2.0//EN">\n<html><head>\n<title>502 Proxy Error</title>\n</head><body>\n<h1>Proxy Error</h1>\n<p>The proxy server received an invalid\r\nresponse from an upstream server.<br />\r\nThe proxy server could not handle the request<p>Reason: <strong>Error reading from remote server</strong></p></p>\n</body></html>\n'"""
    sword_exception = SwordException('ERROR: the server returned malformed xml or a webpage.')
    deposit_record.completed_status = FAILED
    raise CompletionException(err_msg, sword_exception)


def mock_complete_deposit_fail_2(receipt, repo_data, deposit_record, **kwargs):
    err_msg = """<?xml version='1.0' encoding='UTF-8'?>
<sword:error xmlns:dcterms="http://purl.org/dc/terms/" xmlns:sword="http://purl.org/net/sword/terms/" xmlns="http://www.w3.org/2005/Atom"><title>ERROR</title><updated>2020-09-17T10:55:43Z</updated><generator uri="http://www.dspace.org/ns/sword/2.0/" version="2.0">chesterrep@chester.ac.uk</generator><sword:treatment>Processing failed</sword:treatment><summary>The item URL is invalid</summary><sword:verboseDescription>org.swordapp.server.SwordError: The item URL is invalid
        at org.dspace.sword2.SwordUrlManager.getItem(SwordUrlManager.java:131)
        at org.dspace.sword2.ContainerManagerDSpace.getDSpaceTarget(ContainerManagerDSpace.java:863)
        at org.dspace.sword2.ContainerManagerDSpace.useHeaders(ContainerManagerDSpace.java:628)
        at org.swordapp.server.ContainerAPI.post(ContainerAPI.java:359)
        at org.swordapp.server.servlets.ContainerServletDefault.doPost(ContainerServletDefault.java:62)
        at javax.servlet.http.HttpServlet.service(HttpServlet.java:647)
        at javax.servlet.http.HttpServlet.service(HttpServlet.java:728)
        ...
        at org.apache.coyote.http11.AbstractHttp11Processor.process(AbstractHttp11Processor.java:1201)
        at org.apache.coyote.AbstractProtocol$AbstractConnectionHandler.process(AbstractProtocol.java:654)
        at org.apache.tomcat.util.net.JIoEndpoint$SocketProcessor.run(JIoEndpoint.java:317)
        at java.util.concurrent.ThreadPoolExecutor.runWorker(ThreadPoolExecutor.java:1149)
        at java.util.concurrent.ThreadPoolExecutor$Worker.run(ThreadPoolExecutor.java:624)
        at org.apache.tomcat.util.threads.TaskThread$WrappingRunnable.run(TaskThread.java:61)
        at java.lang.Thread.run(Thread.java:748)
</sword:verboseDescription><link rel="alternate" type="text/html" href="https://chesterrep.openrepository.com/contact"/></sword:error>
"""
    deposit_record.completed_status = FAILED
    raise CompletionException(err_msg)

def mock_complete_deposit_fail_3(receipt, repo_data, deposit_record, **kwargs):
    deposit_record.completed_status = FAILED
    raise CompletionException("SWORD Response:\n** NO RESPONSE ***",
                              SwordException('ERROR: the server returned malformed xml or a webpage.'))

def mock_complete_deposit_success(receipt, repo_data, deposit_record, **kwargs):
    deposit_record.completed_status = DEPOSITED
    pass


def mock_get_content_pdf_utf8(url, *args, **kwargs):
    with open(os.path.join(RESOURCES, "test_article.pdf"), "rb") as f:
        file_content = f.read()
    return http.MockResponse(200, file_content, headers={"Content-Type": "application/pdf ;charset=UTF-8"}), "", 0

def mock_get_bad_content_pdf_textplain(url, *args, **kwargs):
    # Open a NON-PDF file, sets "text/plain" Content-Type
    with open(os.path.join(RESOURCES, "README.md"), "rb") as f:
        file_content = f.read()
    return http.MockResponse(200, file_content, headers={"Content-Type": "text/plain"}), "", 0


class TestDeposit(SwordOutTestCase):

    @classmethod
    @app_decorator
    def setUpClass(cls):
        super(TestDeposit, cls).setUpClass()
        current_app.config["STORE_TYPE"] = "local"
        Deposit.init_cls()

    @app_decorator
    def setUp(self):
        super(TestDeposit, self).setUp()
        self.orig_process_notification = Deposit.process_notification
        self.orig_process_account = Deposit.process_account
        self.orig_metadata_deposit = Deposit.metadata_deposit
        self.orig_package_deposit = Deposit.package_deposit_file
        self.orig_complete_deposit = Deposit.complete_deposit
        self.orig_http_get_stream = http.get_stream
        self.orig_iterate = RoutedNotification.routed_scroller_obj
        self.retry_delay = current_app.config.get("DEPOSIT_RETRY_DELAY")
        self.retry_limit = current_app.config.get("DEPOSIT_RETRY_LIMIT")
        # Deposit = Deposit.init_cls()

    @app_decorator
    def tearDown(self):
        # Empty temp store
        Deposit.process_notification = self.orig_process_notification
        Deposit.process_account = self.orig_process_account
        Deposit.metadata_deposit = self.orig_metadata_deposit
        Deposit.package_deposit_file = self.orig_package_deposit
        Deposit.complete_deposit = self.orig_complete_deposit
        http.get_stream = self.orig_http_get_stream
        RoutedNotification.routed_scroller_obj = self.orig_iterate
        current_app.config["DEPOSIT_RETRY_DELAY"] = self.retry_delay
        current_app.config["DEPOSIT_RETRY_LIMIT"] = self.retry_limit
        super(TestDeposit, self).tearDown()

    @classmethod
    def storage_mock_file_create(cls, folder_name, file_name):
        cls.storage_mgr.store(folder_name, file_name, source_data="Test")


    @app_decorator
    def test_01_run_fail(self):
        # create a process_account method that will fail
        Deposit.process_account = mock_process_account_fail

        # create accounts to process
        acc1 = AccountFactory.repo_account(live=True,
                                           org_name="Organization Number 1",
                                           sword_username_pwd_collection_list=["acc1", "pass1", "http://sword/1"])
        acc2 = AccountFactory.repo_account(live=True,
                                           org_name="Organization Number 2",
                                           sword_username_pwd_collection_list=["acc2", "pass2", "http://sword/2"])

        # with fail on error
        with self.assertRaises(DAOException):
            Deposit.send_notes_to_sword_acs()


    @app_decorator
    def test_03_notification_metadata_fail(self):
        # set up the mocks, so that nothing can happen, even if the test goes wrong
        Deposit.metadata_deposit = mock_metadata_deposit_fail
        Deposit.package_deposit_file = mock_package_deposit_file_fail
        Deposit.complete_deposit = mock_complete_deposit_fail

        # create an account to process
        acc = AccountFactory.repo_account()
        
        # create a notification
        note = NotificationFactory.routed_notification(acc.id)

        # get a since date, doesn't really matter what it is
        since = dates.now_str()

        with self.assertRaises(DepositException) as exc:  # because this is what the mock does if it gets called
            Deposit.process_notification(acc, note)
        self.assertIn("Metadata deposit failed", exc.exception.message)

        # nonetheless, this should create a deposit record
        dr = SwordDepositRecord.pull_most_recent_by_note_id_and_repo_id(note.id, acc.id)
        self.assertIsNone(dr)
        drs = SwordDepositRecord.pull_all()
        assert len(drs) == 1
        dr = drs[0]
        self.assertEqual(dr.notification, note.id)
        self.assertEqual(dr.repository, acc.id)
        self.assertTrue(dr.deposit_datestamp >= dates.parse(since))
        self.assertEqual(dr.metadata_status, FAILED)
        self.assertIsNone(dr.content_status)  # because there /is/ content, but we wouldn't have got that far
        self.assertIsNone(dr.completed_status)
        self.assertIn("Metadata deposit failed", dr.error_message)

    @app_decorator
    def test_04_notification_metadata_no_package_success(self):
        # set up the mocks, so that nothing can happen, even if the test goes wrong
        Deposit.metadata_deposit = mock_metadata_deposit_success
        Deposit.package_deposit_file = mock_package_deposit_file_fail
        Deposit.complete_deposit = mock_complete_deposit_fail

        # create an account to process
        acc = AccountFactory.repo_account()
        
        # create a notification without any links in it
        note = NotificationFactory.routed_notification(acc.id, no_links=True)

        since = dates.now_str()
        # process the notification, which we expect to go without error
        Deposit.process_notification(acc, note)

        # this should have created a deposit record
        dr = SwordDepositRecord.pull_most_recent_by_note_id_and_repo_id(note.id, acc.id)
        self.assertIsNotNone(dr)
        self.assertEqual(dr.notification, note.id)
        self.assertEqual(dr.repository, acc.id)
        self.assertTrue(dr.deposit_datestamp >= dates.parse(since))
        self.assertEqual(dr.metadata_status, DEPOSITED)
        self.assertEqual(dr.content_status, None)
        self.assertEqual(dr.completed_status, None)
        self.assertIsNone(dr.error_message)

    @app_decorator
    def test_05_cache_content(self):
        # specify the mock for the http.get function
        http.get_stream = mock_get_content_pdf_utf8

        # create an account to process
        acc = AccountFactory.repo_account()

        fake_url = "url/to/a/pdf/file.pdf"
        link = {
            "type": "fulltext",
            "format": "application/pdf",
            "url": "mock://" + fake_url,   # Doesn't matter what it is as the mock will return a PDF
            "access": "public"
        }

        # technically this is a private method, but it does a single key bit of
        # work so is worth testing it in isolation
        path = Deposit._cache_content(link, "note_id_1234567", acc, "application/pdf")

        self.assertTrue(os.path.isfile(path))

        with open(path, "rb") as f:
            file_content = f.read()

        self.assertIn("PDF", str(file_content))

    @app_decorator
    def test_05_cache_content_pdf_fail(self):
        # specify the mock for the http.get function
        http.get_stream = mock_get_bad_content_pdf_textplain

        # create an account to process
        acc = AccountFactory.repo_account()

        fake_url = "url/to/a/pdf/file.pdf"
        link = {
            "type": "fulltext",
            "format": "application/pdf",
            "url": "mock://" + fake_url,   # Doesn't matter what it is as the mock will return a PDF
            "access": "public"
        }

        # Should raise DespositException as we got plain text file when we wanted a PDF
        with self.assertRaises(GetFileException) as exc:
            Deposit._cache_content(link, "NOTIFICATION_ID", acc, "application/pdf")
        self.assertIn("Unexpected mimetype: 'text/plain'", exc.exception.message)

    @app_decorator
    def test_06_metadata_success_package_fail(self):

        # set up the mocks, so that nothing can happen, even if the test goes wrong
        Deposit.metadata_deposit = mock_metadata_deposit_success
        Deposit.package_deposit_file = mock_package_deposit_file_fail
        Deposit.complete_deposit = mock_complete_deposit_fail

        # create an account to process
        acc = AccountFactory.repo_account()

        # create a notification and keep the links
        note = NotificationFactory.routed_notification(acc.id)

        # get a since date, doesn't really matter what it is
        since = dates.now_str()

        # process the notification, which should throw an exception at the package deposit stage
        with self.assertRaises(DepositException) as exc:
            Deposit.process_notification(acc, note)
        self.assertIn("Complete deposit failed", exc.exception.message)

        # this should have created a deposit record
        dr = SwordDepositRecord.pull_most_recent_by_note_id_and_repo_id(note.id, acc.id)
        self.assertIsNotNone(dr)
        self.assertEqual(dr.notification, note.id)
        self.assertEqual(dr.repository, acc.id)
        self.assertTrue(dr.deposit_datestamp >= dates.parse(since))
        self.assertEqual(dr.metadata_status, DEPOSITED)
        self.assertEqual(dr.content_status, FAILED)
        self.assertEqual(dr.completed_status, FAILED)
        # Expect 2 concatenated errors...
        self.assertIn("Package deposit failed", dr.error_message)
        self.assertIn("Complete deposit failed", dr.error_message)

        tmp_dir = Deposit.temp_store.dir
        dirs = [x for x in os.listdir(tmp_dir) if os.path.isdir(os.path.join(tmp_dir, x))]
        self.assertEqual(0, len(dirs))

    @app_decorator
    def test_06_1_metadata_ok_package_fail_complete_ok(self):
        # set up the mocks, so that nothing can happen, even if the test goes wrong
        Deposit.metadata_deposit = mock_metadata_deposit_success
        Deposit.package_deposit_file = mock_package_deposit_file_fail
        Deposit.complete_deposit = mock_complete_deposit_success

        # create an account to process
        acc = AccountFactory.repo_account()

        # create a notifications
        note_1 = NotificationFactory.routed_notification(acc.id)
        note_2 = NotificationFactory.routed_notification(acc.id)

        current_app.config["DEPOSIT_RETRY_DELAY"] = 0  # so we don't have to wait long
        current_app.config["DEPOSIT_RETRY_LIMIT"] = 0  # so we know exactly how many

        # get a since date, doesn't really matter what it is
        since = dates.now_str()
        Deposit.process_account(acc)

        # One of notifications should have beeb processed, the other not (but we don't know which)
        dr_1 = SwordDepositRecord.pull_most_recent_by_note_id_and_repo_id(note_1.id, acc.id)
        dr_2 = SwordDepositRecord.pull_most_recent_by_note_id_and_repo_id(note_2.id, acc.id)
        self.assertTrue(dr_1 is None or dr_2 is None)
        dr = dr_1 if dr_2 is None else dr_2
        note_id = note_1.id if dr_2 is None else note_2.id
        self.assertIsNotNone(dr)
        self.assertEqual(dr.notification, note_id)
        self.assertEqual(dr.repository, acc.id)
        self.assertTrue(dr.deposit_datestamp >= dates.parse(since))
        self.assertEqual(dr.metadata_status, DEPOSITED)
        self.assertEqual(dr.content_status, FAILED)
        self.assertEqual(dr.completed_status, DEPOSITED)
        self.assertIn("Package deposit failed", dr.error_message)

    @app_decorator
    def test_06_2_metadata_ok_package_fail_complete_fail(self):
        # set up the mocks, so that nothing can happen, even if the test goes wrong
        Deposit.metadata_deposit = mock_metadata_deposit_success
        Depositpackage_deposit_file = mock_package_deposit_file_fail
        Deposit.complete_deposit = mock_complete_deposit_fail

        # create an account to process
        acc = AccountFactory.repo_account()

        # create 2 notification
        note_1 = NotificationFactory.routed_notification(acc.id)
        note_2 = NotificationFactory.routed_notification(acc.id)

        current_app.config["DEPOSIT_RETRY_DELAY"] = 0  # so we don't have to wait long
        current_app.config["DEPOSIT_RETRY_LIMIT"] = 0  # so we know exactly how many

        # get a since date, doesn't really matter what it is
        since = dates.now_str()
        Deposit.process_account(acc)

        # One of notifications should have been processed, the other not (but we don't know which)
        dr_1 = SwordDepositRecord.pull_most_recent_by_note_id_and_repo_id(note_1.id, acc.id)
        dr_2 = SwordDepositRecord.pull_most_recent_by_note_id_and_repo_id(note_2.id, acc.id)
        self.assertTrue(dr_1 is None or dr_2 is None)
        dr = dr_1 if dr_2 is None else dr_2
        note_id = note_1.id if dr_2 is None else note_2.id
        self.assertIsNotNone(dr)
        self.assertEqual(dr.notification, note_id)
        self.assertEqual(dr.repository, acc.id)
        self.assertTrue(dr.deposit_datestamp >= dates.parse(since))
        self.assertEqual(dr.metadata_status, DEPOSITED)
        self.assertEqual(dr.content_status, FAILED)
        self.assertEqual(dr.completed_status, FAILED)
        self.assertIn("Package deposit failed", dr.error_message)
        self.assertIn("Complete deposit failed", dr.error_message)

    @app_decorator
    def test_07_metadata_success_package_success_complete_fail(self):
        # set up the mocks, so that nothing can happen, even if the test goes wrong
        Deposit.metadata_deposit = mock_metadata_deposit_success
        Deposit.package_deposit_file = mock_package_deposit_file_success
        Deposit.complete_deposit = mock_complete_deposit_fail
        mock_folder = "1"
        self.storage_mock_file_create(mock_folder, "ArticleFilesJATS.zip")

        # create an account to process
        acc = AccountFactory.repo_account()

        # create a notification and keep the links
        note = NotificationFactory.routed_notification(acc.id)

        # get a since date, doesn't really matter what it is
        since = dates.now_str()

        # process the notification, which should throw an exception at the final stage
        with self.assertRaises(DepositException) as exc:
            Deposit.process_notification(acc, note)
        self.assertIn("Complete deposit failed", exc.exception.message)
        self.assertIn("Proxy Error", exc.exception.message)

        # storage_mock_file_delete(mock_folder)

        # this should have created a deposit record
        dr = SwordDepositRecord.pull_most_recent_by_note_id_and_repo_id(note.id, acc.id)
        self.assertIsNotNone(dr)
        self.assertEqual(dr.notification, note.id)
        self.assertEqual(dr.repository, acc.id)
        self.assertTrue(dr.deposit_datestamp >= dates.parse(since))
        self.assertEqual(dr.metadata_status, DEPOSITED)
        self.assertEqual(dr.content_status, DEPOSITED)
        self.assertEqual(dr.completed_status, FAILED)
        self.assertIn("Complete deposit failed", dr.error_message)

    @app_decorator
    def test_07_2_metadata_success_package_success_complete_fail(self):
        """
        Same as test_07_metadata.... but with Different error message
        :return:
        """
        # set up the mocks, so that nothing can happen, even if the test goes wrong
        Deposit.metadata_deposit = mock_metadata_deposit_success
        Deposit.package_deposit_file = mock_package_deposit_file_success
        Deposit.complete_deposit = mock_complete_deposit_fail_2  # THIS DIFFERENT FROM PREV TEST
        mock_folder = "1"
        self.storage_mock_file_create(mock_folder, "ArticleFilesJATS.zip")

        # create an account to process
        acc = AccountFactory.repo_account()

        # create a notification and keep the links
        note = NotificationFactory.routed_notification(acc.id)

        # get a since date, doesn't really matter what it is
        since = dates.now_str()

        # process the notification, which should throw an exception at the final stage
        with self.assertRaises(DepositException) as exc:
            Deposit.process_notification(acc, note)
        self.assertIn("Complete deposit failed", exc.exception.message)
        self.assertIn("<sword:error xmlns", exc.exception.message)

        # storage_mock_file_delete(mock_folder)

        # this should have created a deposit record
        dr = SwordDepositRecord.pull_most_recent_by_note_id_and_repo_id(note.id, acc.id)
        self.assertIsNotNone(dr)
        self.assertEqual(dr.notification, note.id)
        self.assertEqual(dr.repository, acc.id)
        self.assertTrue(dr.deposit_datestamp >= dates.parse(since))
        self.assertEqual(dr.metadata_status, DEPOSITED)
        self.assertEqual(dr.content_status, DEPOSITED)
        self.assertEqual(dr.completed_status, FAILED)
        self.assertIn("Complete deposit failed", dr.error_message)
        self.assertIn("<sword:error xmlns", dr.error_message)

    @app_decorator
    def test_08_full_deposit_success(self):
        # set up the mocks, so that nothing can happen, even if the test goes wrong
        Deposit.metadata_deposit = mock_metadata_deposit_success
        Deposit.package_deposit_file = mock_package_deposit_file_success
        Deposit.complete_deposit = mock_complete_deposit_success
        mock_folder = "1"
        self.storage_mock_file_create(mock_folder, "ArticleFilesJATS.zip")

        # create an account to process
        acc = AccountFactory.repo_account()

        # create a notification and keep the links
        note = NotificationFactory.routed_notification(acc.id)

        # get a since date, doesn't really matter what it is
        since = dates.now_str()

        # process the notification, which we expect to go without error
        Deposit.process_notification(acc, note)

        # storage_mock_file_delete(mock_folder)

        # this should have created a deposit record
        dr = SwordDepositRecord.pull_most_recent_by_note_id_and_repo_id(note.id, acc.id)
        self.assertIsNotNone(dr)
        self.assertEqual(dr.notification, note.id)
        self.assertEqual(dr.repository, acc.id)
        self.assertTrue(dr.deposit_datestamp >= dates.parse(since))
        self.assertEqual(dr.metadata_status, DEPOSITED)
        self.assertEqual(dr.content_status, DEPOSITED)
        self.assertEqual(dr.completed_status, DEPOSITED)

    @app_decorator
    def test_09_process_account_failing(self):
        # set up a mock that will fail if the function is called - we shouldn't get that far in this test
        Deposit.process_notification = mock_process_notification_fail

        # create an account to process
        acc = AccountFactory.repo_account(repo_status=FAILING)

        # this should just run and return straight away
        Deposit.process_account(acc)

        # nothing we can really test here, nothing has changed - if we don't get an exception the
        # test is passed

        # now set the status to "problem" but with a timeout that has not yet passed
        acc.repository_data.record_failure(10)
        current_app.config["DEPOSIT_RETRY_DELAY"] = 100  # just to make sure it doesn't expire

        # this should just run and return straight away
        Deposit.process_account(acc)

        # nothing we can really test here, nothing has changed - if we don't get an exception the
        # test is passed

    @app_decorator
    def test_10_1_process_account_scroller_errors(self):
        """
        Various permutations of Exceptions that are raised during scroll process
        """

        # just to prevent anything happening if the test is broken
        Deposit.process_notification = mock_process_notification_success

        # Create an account to process
        acc = AccountFactory.repo_account()


        # make the iterator on JPER that processes 2 notifications & then fails with a DAOException
        # Because this is a DAOException, without abend set, it will NOT cause an exception to be raised from
        # Deposit.send_notes_to_sword_acs
        mocker1 = MockNoteScroller(num_notes=3,
                                   note_ids=101,
                                   exc_to_raise=DAOException("Iterate fail (mock)"),
                                   raise_exc_after=2)
        RoutedNotification.routed_scroller_obj = mocker1.create_mock_note_scroller_obj()
        num_deposits = Deposit.send_notes_to_sword_acs()
        self.assertEqual(3, num_deposits)
        repo_data = AccOrg.pull(acc.id).repository_data
        self.assertEqual(OKAY, repo_data.status)
        self.assertEqual(103, repo_data.last_deposited_note_id)


        # make the iterator on JPER that processes 2 notifications & then fails with a DAOException with abend set
        # Now it SHOULD cause an exception to be raised from Deposit.send_notes_to_sword_acs, but the account will
        # remain in OKAY state (as problem is a Database access exception)
        dao_exc = DAOException("Iterate fail grave (mock)")
        dao_exc.abend = True
        dao_exc.grave = True
        mocker2 = MockNoteScroller(num_notes=3,
                                   note_ids=201,
                                   exc_to_raise=dao_exc,
                                   raise_exc_after=2)
        RoutedNotification.routed_scroller_obj = mocker2.create_mock_note_scroller_obj()
        with self.assertRaises(DAOException) as exc:
            num_deposits = Deposit.send_notes_to_sword_acs()
        self.assertEqual("Iterate fail grave (mock) [ABEND]", str(exc.exception))
        repo_data = AccOrg.pull(acc.id).repository_data
        self.assertEqual(OKAY, repo_data.status)    # Account remains OK state
        self.assertEqual(202, repo_data.last_deposited_note_id)

        # make the iterator on JPER that processes 2 notifications & then fails with a general Exception
        # Now it SHOULD cause an exception to be raised from Deposit.send_notes_to_sword_acs, but the account will
        # remain in OKAY state (as problem is a Database access exception)
        mocker3 = MockNoteScroller(num_notes=3,
                                   note_ids=301,
                                   exc_to_raise=Exception("Iterate fail non DAO error(mock)"),
                                   raise_exc_after=2)

        RoutedNotification.routed_scroller_obj = mocker3.create_mock_note_scroller_obj()
        with self.assertRaises(Exception) as exc:
            num_deposits = Deposit.send_notes_to_sword_acs()
        self.assertEqual("Iterate fail non DAO error(mock)", str(exc.exception))
        repo_data = AccOrg.pull(acc.id).repository_data
        self.assertEqual(FAILING, repo_data.status)     # Note that account NOW set to failing
        self.assertEqual(302, repo_data.last_deposited_note_id)


    @app_decorator
    def test_10_2_process_account_error(self):
        """
        Simulate a problem seen in live:
        - at least 2 accounts
        - processing first account fails with a Completion error
        - ... results in a scroller having unread results
        """
        ## Setup
        # Create 2 accounts
        # Create 2 notifications for each of the accounts
        # For first account simulate a Completion error on the first notification processed, but this should take several seconds to return
        # For 2nd account, there should be no impediment to successful processing.

        sword_data = {
                "username" : "acc1",
                "password" : "pass1",
                "collection" : "http://sword/1",
                "last_updated" : None,
                "last_deposit_date" : None,
                "last_note_id": 0,
                "retries" : 0,
                "last_tried" : None
            }

        # Create 2 accounts to process
        acc1 = AccountFactory.repo_account(live=True,
                                           org_name="Org ONE",
                                           sword_dict=sword_data)
        acc2 = AccountFactory.repo_account(live=True,
                                           org_name="Org TWO",
                                           sword_dict=sword_data,
                                           # These values will overwrite the ones in sword_data
                                           sword_username_pwd_collection_list=["acc2", "pass2", "http://sword/2"])

        # Create 2 notifications for each account
        for ac_id in (acc1.id, acc2.id):
            for x in range(2):
                NotificationFactory.routed_notification(ac_id)

        # set up the mocks, so that nothing can happen, even if the test goes wrong
        # Need to Mock metadata_deposit(...), which should return a valid receipt; _process_link_package_deposit(...);
        # and complete_deposit(...) which should, after an X second delay raise a CompletionException("SWORD Response:\n** NO RESPONSE ***", SwordException('ERROR: the server returned malformed xml or a webpage.'))
        Deposit.metadata_deposit = mock_metadata_deposit_success
        save_plpd = Deposit._process_link_package_deposit
        Deposit._process_link_package_deposit = mock_process_link_package_deposit
        Deposit.complete_deposit = mock_complete_deposit_fail_3

        # deposit.process_account(acc)
        Deposit.send_notes_to_sword_acs()

        Deposit._process_link_package_deposit = save_plpd

        # Account should be set to failing
        repo_data = AccOrg.pull(acc1.id).repository_data
        self.assertIsNotNone(repo_data)
        self.assertEqual(PROBLEM, repo_data.status)
        self.assertEqual(1, repo_data.retries)

    # @patch("octopus.modules.mysql.dao.DAOCursor._cursor_exec")
    @patch("mysql.connector.cursor_cext.CMySQLCursorPrepared.fetchmany")
    @patch("mysql.connector.cursor_cext.CMySQLCursorPrepared.fetchone")
    @app_decorator
    def test_10_3_process_account_note_scroller_lost_conn_error(self, mock_fetchone, mock_fetch):
        """
        Simulate a problem seen in live:
        - at least 2 accounts
        - processing second account notifications fails with a Connection error
        """
        ## Setup
        # Create 2 accounts
        sword_data = {
                "username" : "acc1",
                "password" : "pass1",
                "collection" : "http://sword/1",
                "last_updated" : None,
                "last_deposit_date" : None,
                "last_note_id": 0,
                "retries" : 0,
                "last_tried" : None
            }

        # Create 2 accounts to process
        acc1 = AccountFactory.repo_account(live=True,
                                           org_name="Org ONE",
                                           sword_dict=sword_data)
        acc2 = AccountFactory.repo_account(live=True,
                                           org_name="Org TWO",
                                           sword_dict=sword_data,
                                           # These values will overwrite the ones in sword_data
                                           sword_username_pwd_collection_list=["acc2", "pass2", "http://sword/2"])

        # set up the mocks, so that nothing can happen, even if the test goes wrong
        Deposit.metadata_deposit = mock_metadata_deposit_success
        save_plpd = Deposit._process_link_package_deposit
        Deposit._process_link_package_deposit = mock_process_link_package_deposit
        Deposit.complete_deposit = mock_complete_deposit_success

        mock_fetch.side_effect = [
            ## Notifications for first account (with Id 2)
            # First tranche of 5 records (for Ac with Id 2)
            [
                (1, datetime.datetime(2023, 8, 25, 17, 15, 3), 'R', datetime.datetime(2023, 8, 25, 17, 15, 3),
                 '55.aa/base.1', 8, None, 'Wiley Fox', 'ftp', 1, '2', 'https://pubrouter.jisc.ac.uk/FilesAndJATS',
                 '[{"type":"splash","format":"text/html","url":"http://external_domain.com/some/url","access":"public"},{"type":"fulltext","format":"application/pdf","access":"router","cloc":"testfile.pdf"},{"type":"package","format":"application/zip","access":"router","packaging":"http://purl.org/net/sword/package/SimpleZip","cloc":"ArticleFilesJATS.zip"},{"type":"package","format":"application/zip","access":"router","packaging":"https://pubrouter.jisc.ac.uk/FilesAndJATS","cloc":""}]',
                 None,
                 '{"event":"publication","vers":"4","content":{},"metadata":{"publication_status":"Published","accepted_date":"2014-09-01","peer_reviewed":true,"ack":"Some acknowledgement text","journal":{"title":"Journal of Important Things","abbrev_title":"Abbreviated version of journal  title","volume":"Volume-number","issue":"Issue-number","publisher":["Premier Publisher"],"identifier":[{"type":"issn","id":"1234-5678"},{"type":"eissn","id":"1234-5678"},{"type":"pissn","id":"9876-5432"},{"type":"doi","id":"10.pp/jit"}]},"article":{"title":"Test Article","type":"research-article","version":"AAM","start_page":"Start-pg","end_page":"End-pg","page_range":"Page-range","num_pages":"Total-pages","e_num":"e-Location","abstract":"Abstract of the work. Sed ut perspiciatis unde omnis iste natus error sit voluptatem accusantium doloremque laudantium, totam rem aperiam, eaque ipsa quae ab illo inventore veritatis et quasi architecto beatae vitae dicta sunt explicabo.","subtitle":["Test Article Subtitle"],"language":["en"],"subject":["Science","New Technology","Medicine"],"identifier":[{"type":"doi","id":"55.aa/base.1"},{"type":"publisher-id","id":"pub-15-51689"}]},"publication_date":{"publication_format":"electronic","date":"2015-01-05","year":"2015","month":"01","day":"05","season":""},"embargo":{"start":"","end":"2015-07-05","duration":"180"},"author":[{"type":"corresp","organisation_name":"Grottage Labs","name":{"firstname":"Richard","surname":"Jones","fullname":"Richard Jones","suffix":""},"identifier":[{"type":"orcid","id":"3333-0000-1111-2222"},{"type":"email","id":"richard@example.com"}],"affiliations":[{"org":"Cottage Labs org","dept":"Moonshine dept","street":"Lame street","city":"Cardiff","state":"Gwent","postcode":"HP3 9AA","country":"England","country_code":"GB","raw":"Cottage Labs org, Moonshine dept, Lame street, Cardiff, Gwent, HP3 9AA, England, ISNI: isni 1111 2222 3333, ROR: ror-123","identifier":[{"type":"ISNI","id":"isni 1111 2222 3333"},{"type":"ROR","id":"ror-123"}]}]},{"type":"author","organisation_name":"","name":{"firstname":"Mark","surname":"MacGillivray","fullname":"Mark MacGillivray"},"identifier":[{"type":"orcid","id":"1111-2222-3333-0000"},{"type":"email","id":"mark@example.com"}],"affiliations":[{"raw":"Cottage Labs, EH9 5TP"}]},{"type":"author","name":{"firstname":"Kuan-Meng","surname":"Soo","fullname":"Soo, Kuan-Meng"},"identifier":[{"type":"orcid","id":"0000-0001-7744-0424"}],"affiliations":[{"raw":"Department of Microbiology and Parasitology, Faculty of Medicine and Health Sciences, Universiti Putra Malaysia, Serdang, Selangor, Malaysia"}]},{"type":"author","organisation_name":"Author organisation only (no name)","affiliations":[{"raw":"Org name only"}]}],"contributor":[{"type":"editor","organisation_name":"ACME Org Name","name":{"firstname":"Manolo","surname":"Williams","fullname":"Manolo Williams"},"identifier":[{"type":"email","id":"manolo@example.com"}],"affiliations":[{"raw":"Lalala Labs, BS1 8HD"}]},{"type":"reviewer","organisation_name":"Contributor organisation only","identifier":[{"type":"email","id":"contrib-org@example.com"}],"affiliations":[{"raw":"Lalalalala Labs, BS1 8HD"}]}],"funding":[{"name":"Ministry of Higher Education, Malaysia","identifier":[{"type":"funder-id","id":"http://dx.doi.org/10.13039/501100003093"}],"grant_numbers":["LR001/2011A"]},{"name":"Rotary Club of Eureka","identifier":[{"type":"ringgold","id":"rot-club-eurek"},{"type":"Fundref","id":"10.13039/100008650"}],"grant_numbers":["BB/34/juwef","BB/35/juwef"]}],"license_ref":[{"title":"This is an open access article distributed in accordance with the Creative Commons Attribution 4.0 Unported (CC BY 4.0) license, which permits others to copy, redistribute, remix, transform and build upon this work for any purpose, provided the original work is properly cited, a link to the licence is given, and indication of whether changes were made. See: https://creativecommons.org/licenses/by/4.0/.","type":"open-access","url":"https://creativecommons.org/licenses/by/4.0/","version":"4.0","start":"2015-07-05"},{"title":"licence title","type":"restricted","url":"http://license-url","version":"1","start":"2022-01-02"}]},"provider":{}}'),
                (2, datetime.datetime(2023, 8, 25, 17, 15, 3), 'R', datetime.datetime(2023, 8, 25, 17, 15, 3),
                 '55.aa/base.1', 8, None, 'Wiley Fox', 'ftp', 1, '2', 'https://pubrouter.jisc.ac.uk/FilesAndJATS',
                 '[{"type":"splash","format":"text/html","url":"http://external_domain.com/some/url","access":"public"},{"type":"fulltext","format":"application/pdf","access":"router","cloc":"testfile.pdf"},{"type":"package","format":"application/zip","access":"router","packaging":"http://purl.org/net/sword/package/SimpleZip","cloc":"ArticleFilesJATS.zip"},{"type":"package","format":"application/zip","access":"router","packaging":"https://pubrouter.jisc.ac.uk/FilesAndJATS","cloc":""}]',
                 None,
                 '{"event":"publication","vers":"4","content":{},"metadata":{"publication_status":"Published","accepted_date":"2014-09-01","peer_reviewed":true,"ack":"Some acknowledgement text","journal":{"title":"Journal of Important Things","abbrev_title":"Abbreviated version of journal  title","volume":"Volume-number","issue":"Issue-number","publisher":["Premier Publisher"],"identifier":[{"type":"issn","id":"1234-5678"},{"type":"eissn","id":"1234-5678"},{"type":"pissn","id":"9876-5432"},{"type":"doi","id":"10.pp/jit"}]},"article":{"title":"Test Article","type":"research-article","version":"AAM","start_page":"Start-pg","end_page":"End-pg","page_range":"Page-range","num_pages":"Total-pages","e_num":"e-Location","abstract":"Abstract of the work. Sed ut perspiciatis unde omnis iste natus error sit voluptatem accusantium doloremque laudantium, totam rem aperiam, eaque ipsa quae ab illo inventore veritatis et quasi architecto beatae vitae dicta sunt explicabo.","subtitle":["Test Article Subtitle"],"language":["en"],"subject":["Science","New Technology","Medicine"],"identifier":[{"type":"doi","id":"55.aa/base.1"},{"type":"publisher-id","id":"pub-15-51689"}]},"publication_date":{"publication_format":"electronic","date":"2015-01-05","year":"2015","month":"01","day":"05","season":""},"embargo":{"start":"","end":"2015-07-05","duration":"180"},"author":[{"type":"corresp","organisation_name":"Grottage Labs","name":{"firstname":"Richard","surname":"Jones","fullname":"Richard Jones","suffix":""},"identifier":[{"type":"orcid","id":"3333-0000-1111-2222"},{"type":"email","id":"richard@example.com"}],"affiliations":[{"org":"Cottage Labs org","dept":"Moonshine dept","street":"Lame street","city":"Cardiff","state":"Gwent","postcode":"HP3 9AA","country":"England","country_code":"GB","raw":"Cottage Labs org, Moonshine dept, Lame street, Cardiff, Gwent, HP3 9AA, England, ISNI: isni 1111 2222 3333, ROR: ror-123","identifier":[{"type":"ISNI","id":"isni 1111 2222 3333"},{"type":"ROR","id":"ror-123"}]}]},{"type":"author","organisation_name":"","name":{"firstname":"Mark","surname":"MacGillivray","fullname":"Mark MacGillivray"},"identifier":[{"type":"orcid","id":"1111-2222-3333-0000"},{"type":"email","id":"mark@example.com"}],"affiliations":[{"raw":"Cottage Labs, EH9 5TP"}]},{"type":"author","name":{"firstname":"Kuan-Meng","surname":"Soo","fullname":"Soo, Kuan-Meng"},"identifier":[{"type":"orcid","id":"0000-0001-7744-0424"}],"affiliations":[{"raw":"Department of Microbiology and Parasitology, Faculty of Medicine and Health Sciences, Universiti Putra Malaysia, Serdang, Selangor, Malaysia"}]},{"type":"author","organisation_name":"Author organisation only (no name)","affiliations":[{"raw":"Org name only"}]}],"contributor":[{"type":"editor","organisation_name":"ACME Org Name","name":{"firstname":"Manolo","surname":"Williams","fullname":"Manolo Williams"},"identifier":[{"type":"email","id":"manolo@example.com"}],"affiliations":[{"raw":"Lalala Labs, BS1 8HD"}]},{"type":"reviewer","organisation_name":"Contributor organisation only","identifier":[{"type":"email","id":"contrib-org@example.com"}],"affiliations":[{"raw":"Lalalalala Labs, BS1 8HD"}]}],"funding":[{"name":"Ministry of Higher Education, Malaysia","identifier":[{"type":"funder-id","id":"http://dx.doi.org/10.13039/501100003093"}],"grant_numbers":["LR001/2011A"]},{"name":"Rotary Club of Eureka","identifier":[{"type":"ringgold","id":"rot-club-eurek"},{"type":"Fundref","id":"10.13039/100008650"}],"grant_numbers":["BB/34/juwef","BB/35/juwef"]}],"license_ref":[{"title":"This is an open access article distributed in accordance with the Creative Commons Attribution 4.0 Unported (CC BY 4.0) license, which permits others to copy, redistribute, remix, transform and build upon this work for any purpose, provided the original work is properly cited, a link to the licence is given, and indication of whether changes were made. See: https://creativecommons.org/licenses/by/4.0/.","type":"open-access","url":"https://creativecommons.org/licenses/by/4.0/","version":"4.0","start":"2015-07-05"},{"title":"licence title","type":"restricted","url":"http://license-url","version":"1","start":"2022-01-02"}]},"provider":{}}'),
                (3, datetime.datetime(2023, 8, 25, 17, 15, 3), 'R', datetime.datetime(2023, 8, 25, 17, 15, 3),
                 '55.aa/base.1', 8, None, 'Wiley Fox', 'ftp', 1, '2', 'https://pubrouter.jisc.ac.uk/FilesAndJATS',
                 '[{"type":"splash","format":"text/html","url":"http://external_domain.com/some/url","access":"public"},{"type":"fulltext","format":"application/pdf","access":"router","cloc":"testfile.pdf"},{"type":"package","format":"application/zip","access":"router","packaging":"http://purl.org/net/sword/package/SimpleZip","cloc":"ArticleFilesJATS.zip"},{"type":"package","format":"application/zip","access":"router","packaging":"https://pubrouter.jisc.ac.uk/FilesAndJATS","cloc":""}]',
                 None,
                 '{"event":"publication","vers":"4","content":{},"metadata":{"publication_status":"Published","accepted_date":"2014-09-01","peer_reviewed":true,"ack":"Some acknowledgement text","journal":{"title":"Journal of Important Things","abbrev_title":"Abbreviated version of journal  title","volume":"Volume-number","issue":"Issue-number","publisher":["Premier Publisher"],"identifier":[{"type":"issn","id":"1234-5678"},{"type":"eissn","id":"1234-5678"},{"type":"pissn","id":"9876-5432"},{"type":"doi","id":"10.pp/jit"}]},"article":{"title":"Test Article","type":"research-article","version":"AAM","start_page":"Start-pg","end_page":"End-pg","page_range":"Page-range","num_pages":"Total-pages","e_num":"e-Location","abstract":"Abstract of the work. Sed ut perspiciatis unde omnis iste natus error sit voluptatem accusantium doloremque laudantium, totam rem aperiam, eaque ipsa quae ab illo inventore veritatis et quasi architecto beatae vitae dicta sunt explicabo.","subtitle":["Test Article Subtitle"],"language":["en"],"subject":["Science","New Technology","Medicine"],"identifier":[{"type":"doi","id":"55.aa/base.1"},{"type":"publisher-id","id":"pub-15-51689"}]},"publication_date":{"publication_format":"electronic","date":"2015-01-05","year":"2015","month":"01","day":"05","season":""},"embargo":{"start":"","end":"2015-07-05","duration":"180"},"author":[{"type":"corresp","organisation_name":"Grottage Labs","name":{"firstname":"Richard","surname":"Jones","fullname":"Richard Jones","suffix":""},"identifier":[{"type":"orcid","id":"3333-0000-1111-2222"},{"type":"email","id":"richard@example.com"}],"affiliations":[{"org":"Cottage Labs org","dept":"Moonshine dept","street":"Lame street","city":"Cardiff","state":"Gwent","postcode":"HP3 9AA","country":"England","country_code":"GB","raw":"Cottage Labs org, Moonshine dept, Lame street, Cardiff, Gwent, HP3 9AA, England, ISNI: isni 1111 2222 3333, ROR: ror-123","identifier":[{"type":"ISNI","id":"isni 1111 2222 3333"},{"type":"ROR","id":"ror-123"}]}]},{"type":"author","organisation_name":"","name":{"firstname":"Mark","surname":"MacGillivray","fullname":"Mark MacGillivray"},"identifier":[{"type":"orcid","id":"1111-2222-3333-0000"},{"type":"email","id":"mark@example.com"}],"affiliations":[{"raw":"Cottage Labs, EH9 5TP"}]},{"type":"author","name":{"firstname":"Kuan-Meng","surname":"Soo","fullname":"Soo, Kuan-Meng"},"identifier":[{"type":"orcid","id":"0000-0001-7744-0424"}],"affiliations":[{"raw":"Department of Microbiology and Parasitology, Faculty of Medicine and Health Sciences, Universiti Putra Malaysia, Serdang, Selangor, Malaysia"}]},{"type":"author","organisation_name":"Author organisation only (no name)","affiliations":[{"raw":"Org name only"}]}],"contributor":[{"type":"editor","organisation_name":"ACME Org Name","name":{"firstname":"Manolo","surname":"Williams","fullname":"Manolo Williams"},"identifier":[{"type":"email","id":"manolo@example.com"}],"affiliations":[{"raw":"Lalala Labs, BS1 8HD"}]},{"type":"reviewer","organisation_name":"Contributor organisation only","identifier":[{"type":"email","id":"contrib-org@example.com"}],"affiliations":[{"raw":"Lalalalala Labs, BS1 8HD"}]}],"funding":[{"name":"Ministry of Higher Education, Malaysia","identifier":[{"type":"funder-id","id":"http://dx.doi.org/10.13039/501100003093"}],"grant_numbers":["LR001/2011A"]},{"name":"Rotary Club of Eureka","identifier":[{"type":"ringgold","id":"rot-club-eurek"},{"type":"Fundref","id":"10.13039/100008650"}],"grant_numbers":["BB/34/juwef","BB/35/juwef"]}],"license_ref":[{"title":"This is an open access article distributed in accordance with the Creative Commons Attribution 4.0 Unported (CC BY 4.0) license, which permits others to copy, redistribute, remix, transform and build upon this work for any purpose, provided the original work is properly cited, a link to the licence is given, and indication of whether changes were made. See: https://creativecommons.org/licenses/by/4.0/.","type":"open-access","url":"https://creativecommons.org/licenses/by/4.0/","version":"4.0","start":"2015-07-05"},{"title":"licence title","type":"restricted","url":"http://license-url","version":"1","start":"2022-01-02"}]},"provider":{}}'),
                (4, datetime.datetime(2023, 8, 25, 17, 15, 3), 'R', datetime.datetime(2023, 8, 25, 17, 15, 3),
                 '55.aa/base.1', 8, None, 'Wiley Fox', 'ftp', 1, '2', 'https://pubrouter.jisc.ac.uk/FilesAndJATS',
                 '[{"type":"splash","format":"text/html","url":"http://external_domain.com/some/url","access":"public"},{"type":"fulltext","format":"application/pdf","access":"router","cloc":"testfile.pdf"},{"type":"package","format":"application/zip","access":"router","packaging":"http://purl.org/net/sword/package/SimpleZip","cloc":"ArticleFilesJATS.zip"},{"type":"package","format":"application/zip","access":"router","packaging":"https://pubrouter.jisc.ac.uk/FilesAndJATS","cloc":""}]',
                 None,
                 '{"event":"publication","vers":"4","content":{},"metadata":{"publication_status":"Published","accepted_date":"2014-09-01","peer_reviewed":true,"ack":"Some acknowledgement text","journal":{"title":"Journal of Important Things","abbrev_title":"Abbreviated version of journal  title","volume":"Volume-number","issue":"Issue-number","publisher":["Premier Publisher"],"identifier":[{"type":"issn","id":"1234-5678"},{"type":"eissn","id":"1234-5678"},{"type":"pissn","id":"9876-5432"},{"type":"doi","id":"10.pp/jit"}]},"article":{"title":"Test Article","type":"research-article","version":"AAM","start_page":"Start-pg","end_page":"End-pg","page_range":"Page-range","num_pages":"Total-pages","e_num":"e-Location","abstract":"Abstract of the work. Sed ut perspiciatis unde omnis iste natus error sit voluptatem accusantium doloremque laudantium, totam rem aperiam, eaque ipsa quae ab illo inventore veritatis et quasi architecto beatae vitae dicta sunt explicabo.","subtitle":["Test Article Subtitle"],"language":["en"],"subject":["Science","New Technology","Medicine"],"identifier":[{"type":"doi","id":"55.aa/base.1"},{"type":"publisher-id","id":"pub-15-51689"}]},"publication_date":{"publication_format":"electronic","date":"2015-01-05","year":"2015","month":"01","day":"05","season":""},"embargo":{"start":"","end":"2015-07-05","duration":"180"},"author":[{"type":"corresp","organisation_name":"Grottage Labs","name":{"firstname":"Richard","surname":"Jones","fullname":"Richard Jones","suffix":""},"identifier":[{"type":"orcid","id":"3333-0000-1111-2222"},{"type":"email","id":"richard@example.com"}],"affiliations":[{"org":"Cottage Labs org","dept":"Moonshine dept","street":"Lame street","city":"Cardiff","state":"Gwent","postcode":"HP3 9AA","country":"England","country_code":"GB","raw":"Cottage Labs org, Moonshine dept, Lame street, Cardiff, Gwent, HP3 9AA, England, ISNI: isni 1111 2222 3333, ROR: ror-123","identifier":[{"type":"ISNI","id":"isni 1111 2222 3333"},{"type":"ROR","id":"ror-123"}]}]},{"type":"author","organisation_name":"","name":{"firstname":"Mark","surname":"MacGillivray","fullname":"Mark MacGillivray"},"identifier":[{"type":"orcid","id":"1111-2222-3333-0000"},{"type":"email","id":"mark@example.com"}],"affiliations":[{"raw":"Cottage Labs, EH9 5TP"}]},{"type":"author","name":{"firstname":"Kuan-Meng","surname":"Soo","fullname":"Soo, Kuan-Meng"},"identifier":[{"type":"orcid","id":"0000-0001-7744-0424"}],"affiliations":[{"raw":"Department of Microbiology and Parasitology, Faculty of Medicine and Health Sciences, Universiti Putra Malaysia, Serdang, Selangor, Malaysia"}]},{"type":"author","organisation_name":"Author organisation only (no name)","affiliations":[{"raw":"Org name only"}]}],"contributor":[{"type":"editor","organisation_name":"ACME Org Name","name":{"firstname":"Manolo","surname":"Williams","fullname":"Manolo Williams"},"identifier":[{"type":"email","id":"manolo@example.com"}],"affiliations":[{"raw":"Lalala Labs, BS1 8HD"}]},{"type":"reviewer","organisation_name":"Contributor organisation only","identifier":[{"type":"email","id":"contrib-org@example.com"}],"affiliations":[{"raw":"Lalalalala Labs, BS1 8HD"}]}],"funding":[{"name":"Ministry of Higher Education, Malaysia","identifier":[{"type":"funder-id","id":"http://dx.doi.org/10.13039/501100003093"}],"grant_numbers":["LR001/2011A"]},{"name":"Rotary Club of Eureka","identifier":[{"type":"ringgold","id":"rot-club-eurek"},{"type":"Fundref","id":"10.13039/100008650"}],"grant_numbers":["BB/34/juwef","BB/35/juwef"]}],"license_ref":[{"title":"This is an open access article distributed in accordance with the Creative Commons Attribution 4.0 Unported (CC BY 4.0) license, which permits others to copy, redistribute, remix, transform and build upon this work for any purpose, provided the original work is properly cited, a link to the licence is given, and indication of whether changes were made. See: https://creativecommons.org/licenses/by/4.0/.","type":"open-access","url":"https://creativecommons.org/licenses/by/4.0/","version":"4.0","start":"2015-07-05"},{"title":"licence title","type":"restricted","url":"http://license-url","version":"1","start":"2022-01-02"}]},"provider":{}}'),
                (5, datetime.datetime(2023, 8, 25, 17, 15, 3), 'R', datetime.datetime(2023, 8, 25, 17, 15, 3),
                 '55.aa/base.1', 8, None, 'Wiley Fox', 'ftp', 1, '2', 'https://pubrouter.jisc.ac.uk/FilesAndJATS',
                 '[{"type":"splash","format":"text/html","url":"http://external_domain.com/some/url","access":"public"},{"type":"fulltext","format":"application/pdf","access":"router","cloc":"testfile.pdf"},{"type":"package","format":"application/zip","access":"router","packaging":"http://purl.org/net/sword/package/SimpleZip","cloc":"ArticleFilesJATS.zip"},{"type":"package","format":"application/zip","access":"router","packaging":"https://pubrouter.jisc.ac.uk/FilesAndJATS","cloc":""}]',
                 None,
                 '{"event":"publication","vers":"4","content":{},"metadata":{"publication_status":"Published","accepted_date":"2014-09-01","peer_reviewed":true,"ack":"Some acknowledgement text","journal":{"title":"Journal of Important Things","abbrev_title":"Abbreviated version of journal  title","volume":"Volume-number","issue":"Issue-number","publisher":["Premier Publisher"],"identifier":[{"type":"issn","id":"1234-5678"},{"type":"eissn","id":"1234-5678"},{"type":"pissn","id":"9876-5432"},{"type":"doi","id":"10.pp/jit"}]},"article":{"title":"Test Article","type":"research-article","version":"AAM","start_page":"Start-pg","end_page":"End-pg","page_range":"Page-range","num_pages":"Total-pages","e_num":"e-Location","abstract":"Abstract of the work. Sed ut perspiciatis unde omnis iste natus error sit voluptatem accusantium doloremque laudantium, totam rem aperiam, eaque ipsa quae ab illo inventore veritatis et quasi architecto beatae vitae dicta sunt explicabo.","subtitle":["Test Article Subtitle"],"language":["en"],"subject":["Science","New Technology","Medicine"],"identifier":[{"type":"doi","id":"55.aa/base.1"},{"type":"publisher-id","id":"pub-15-51689"}]},"publication_date":{"publication_format":"electronic","date":"2015-01-05","year":"2015","month":"01","day":"05","season":""},"embargo":{"start":"","end":"2015-07-05","duration":"180"},"author":[{"type":"corresp","organisation_name":"Grottage Labs","name":{"firstname":"Richard","surname":"Jones","fullname":"Richard Jones","suffix":""},"identifier":[{"type":"orcid","id":"3333-0000-1111-2222"},{"type":"email","id":"richard@example.com"}],"affiliations":[{"org":"Cottage Labs org","dept":"Moonshine dept","street":"Lame street","city":"Cardiff","state":"Gwent","postcode":"HP3 9AA","country":"England","country_code":"GB","raw":"Cottage Labs org, Moonshine dept, Lame street, Cardiff, Gwent, HP3 9AA, England, ISNI: isni 1111 2222 3333, ROR: ror-123","identifier":[{"type":"ISNI","id":"isni 1111 2222 3333"},{"type":"ROR","id":"ror-123"}]}]},{"type":"author","organisation_name":"","name":{"firstname":"Mark","surname":"MacGillivray","fullname":"Mark MacGillivray"},"identifier":[{"type":"orcid","id":"1111-2222-3333-0000"},{"type":"email","id":"mark@example.com"}],"affiliations":[{"raw":"Cottage Labs, EH9 5TP"}]},{"type":"author","name":{"firstname":"Kuan-Meng","surname":"Soo","fullname":"Soo, Kuan-Meng"},"identifier":[{"type":"orcid","id":"0000-0001-7744-0424"}],"affiliations":[{"raw":"Department of Microbiology and Parasitology, Faculty of Medicine and Health Sciences, Universiti Putra Malaysia, Serdang, Selangor, Malaysia"}]},{"type":"author","organisation_name":"Author organisation only (no name)","affiliations":[{"raw":"Org name only"}]}],"contributor":[{"type":"editor","organisation_name":"ACME Org Name","name":{"firstname":"Manolo","surname":"Williams","fullname":"Manolo Williams"},"identifier":[{"type":"email","id":"manolo@example.com"}],"affiliations":[{"raw":"Lalala Labs, BS1 8HD"}]},{"type":"reviewer","organisation_name":"Contributor organisation only","identifier":[{"type":"email","id":"contrib-org@example.com"}],"affiliations":[{"raw":"Lalalalala Labs, BS1 8HD"}]}],"funding":[{"name":"Ministry of Higher Education, Malaysia","identifier":[{"type":"funder-id","id":"http://dx.doi.org/10.13039/501100003093"}],"grant_numbers":["LR001/2011A"]},{"name":"Rotary Club of Eureka","identifier":[{"type":"ringgold","id":"rot-club-eurek"},{"type":"Fundref","id":"10.13039/100008650"}],"grant_numbers":["BB/34/juwef","BB/35/juwef"]}],"license_ref":[{"title":"This is an open access article distributed in accordance with the Creative Commons Attribution 4.0 Unported (CC BY 4.0) license, which permits others to copy, redistribute, remix, transform and build upon this work for any purpose, provided the original work is properly cited, a link to the licence is given, and indication of whether changes were made. See: https://creativecommons.org/licenses/by/4.0/.","type":"open-access","url":"https://creativecommons.org/licenses/by/4.0/","version":"4.0","start":"2015-07-05"},{"title":"licence title","type":"restricted","url":"http://license-url","version":"1","start":"2022-01-02"}]},"provider":{}}'),
             ],

            # 2nd tranch of records (for Ac with Id 2) (just 5 recs)
            [
                (11, datetime.datetime(2023, 8, 25, 17, 15, 3), 'R', datetime.datetime(2023, 8, 25, 17, 15, 3),
                 '55.aa/base.1', 8, None, 'Wiley Fox', 'ftp', 1, '2', 'https://pubrouter.jisc.ac.uk/FilesAndJATS',
                 '[{"type":"splash","format":"text/html","url":"http://external_domain.com/some/url","access":"public"},{"type":"fulltext","format":"application/pdf","access":"router","cloc":"testfile.pdf"},{"type":"package","format":"application/zip","access":"router","packaging":"http://purl.org/net/sword/package/SimpleZip","cloc":"ArticleFilesJATS.zip"},{"type":"package","format":"application/zip","access":"router","packaging":"https://pubrouter.jisc.ac.uk/FilesAndJATS","cloc":""}]',
                 None,
                 '{"event":"publication","vers":"4","content":{},"metadata":{"publication_status":"Published","accepted_date":"2014-09-01","peer_reviewed":true,"ack":"Some acknowledgement text","journal":{"title":"Journal of Important Things","abbrev_title":"Abbreviated version of journal  title","volume":"Volume-number","issue":"Issue-number","publisher":["Premier Publisher"],"identifier":[{"type":"issn","id":"1234-5678"},{"type":"eissn","id":"1234-5678"},{"type":"pissn","id":"9876-5432"},{"type":"doi","id":"10.pp/jit"}]},"article":{"title":"Test Article","type":"research-article","version":"AAM","start_page":"Start-pg","end_page":"End-pg","page_range":"Page-range","num_pages":"Total-pages","e_num":"e-Location","abstract":"Abstract of the work. Sed ut perspiciatis unde omnis iste natus error sit voluptatem accusantium doloremque laudantium, totam rem aperiam, eaque ipsa quae ab illo inventore veritatis et quasi architecto beatae vitae dicta sunt explicabo.","subtitle":["Test Article Subtitle"],"language":["en"],"subject":["Science","New Technology","Medicine"],"identifier":[{"type":"doi","id":"55.aa/base.1"},{"type":"publisher-id","id":"pub-15-51689"}]},"publication_date":{"publication_format":"electronic","date":"2015-01-05","year":"2015","month":"01","day":"05","season":""},"embargo":{"start":"","end":"2015-07-05","duration":"180"},"author":[{"type":"corresp","organisation_name":"Grottage Labs","name":{"firstname":"Richard","surname":"Jones","fullname":"Richard Jones","suffix":""},"identifier":[{"type":"orcid","id":"3333-0000-1111-2222"},{"type":"email","id":"richard@example.com"}],"affiliations":[{"org":"Cottage Labs org","dept":"Moonshine dept","street":"Lame street","city":"Cardiff","state":"Gwent","postcode":"HP3 9AA","country":"England","country_code":"GB","raw":"Cottage Labs org, Moonshine dept, Lame street, Cardiff, Gwent, HP3 9AA, England, ISNI: isni 1111 2222 3333, ROR: ror-123","identifier":[{"type":"ISNI","id":"isni 1111 2222 3333"},{"type":"ROR","id":"ror-123"}]}]},{"type":"author","organisation_name":"","name":{"firstname":"Mark","surname":"MacGillivray","fullname":"Mark MacGillivray"},"identifier":[{"type":"orcid","id":"1111-2222-3333-0000"},{"type":"email","id":"mark@example.com"}],"affiliations":[{"raw":"Cottage Labs, EH9 5TP"}]},{"type":"author","name":{"firstname":"Kuan-Meng","surname":"Soo","fullname":"Soo, Kuan-Meng"},"identifier":[{"type":"orcid","id":"0000-0001-7744-0424"}],"affiliations":[{"raw":"Department of Microbiology and Parasitology, Faculty of Medicine and Health Sciences, Universiti Putra Malaysia, Serdang, Selangor, Malaysia"}]},{"type":"author","organisation_name":"Author organisation only (no name)","affiliations":[{"raw":"Org name only"}]}],"contributor":[{"type":"editor","organisation_name":"ACME Org Name","name":{"firstname":"Manolo","surname":"Williams","fullname":"Manolo Williams"},"identifier":[{"type":"email","id":"manolo@example.com"}],"affiliations":[{"raw":"Lalala Labs, BS1 8HD"}]},{"type":"reviewer","organisation_name":"Contributor organisation only","identifier":[{"type":"email","id":"contrib-org@example.com"}],"affiliations":[{"raw":"Lalalalala Labs, BS1 8HD"}]}],"funding":[{"name":"Ministry of Higher Education, Malaysia","identifier":[{"type":"funder-id","id":"http://dx.doi.org/10.13039/501100003093"}],"grant_numbers":["LR001/2011A"]},{"name":"Rotary Club of Eureka","identifier":[{"type":"ringgold","id":"rot-club-eurek"},{"type":"Fundref","id":"10.13039/100008650"}],"grant_numbers":["BB/34/juwef","BB/35/juwef"]}],"license_ref":[{"title":"This is an open access article distributed in accordance with the Creative Commons Attribution 4.0 Unported (CC BY 4.0) license, which permits others to copy, redistribute, remix, transform and build upon this work for any purpose, provided the original work is properly cited, a link to the licence is given, and indication of whether changes were made. See: https://creativecommons.org/licenses/by/4.0/.","type":"open-access","url":"https://creativecommons.org/licenses/by/4.0/","version":"4.0","start":"2015-07-05"},{"title":"licence title","type":"restricted","url":"http://license-url","version":"1","start":"2022-01-02"}]},"provider":{}}'),
                (12, datetime.datetime(2023, 8, 25, 17, 15, 3), 'R', datetime.datetime(2023, 8, 25, 17, 15, 3),
                 '55.aa/base.1', 8, None, 'Wiley Fox', 'ftp', 1, '2', 'https://pubrouter.jisc.ac.uk/FilesAndJATS',
                 '[{"type":"splash","format":"text/html","url":"http://external_domain.com/some/url","access":"public"},{"type":"fulltext","format":"application/pdf","access":"router","cloc":"testfile.pdf"},{"type":"package","format":"application/zip","access":"router","packaging":"http://purl.org/net/sword/package/SimpleZip","cloc":"ArticleFilesJATS.zip"},{"type":"package","format":"application/zip","access":"router","packaging":"https://pubrouter.jisc.ac.uk/FilesAndJATS","cloc":""}]',
                 None,
                 '{"event":"publication","vers":"4","content":{},"metadata":{"publication_status":"Published","accepted_date":"2014-09-01","peer_reviewed":true,"ack":"Some acknowledgement text","journal":{"title":"Journal of Important Things","abbrev_title":"Abbreviated version of journal  title","volume":"Volume-number","issue":"Issue-number","publisher":["Premier Publisher"],"identifier":[{"type":"issn","id":"1234-5678"},{"type":"eissn","id":"1234-5678"},{"type":"pissn","id":"9876-5432"},{"type":"doi","id":"10.pp/jit"}]},"article":{"title":"Test Article","type":"research-article","version":"AAM","start_page":"Start-pg","end_page":"End-pg","page_range":"Page-range","num_pages":"Total-pages","e_num":"e-Location","abstract":"Abstract of the work. Sed ut perspiciatis unde omnis iste natus error sit voluptatem accusantium doloremque laudantium, totam rem aperiam, eaque ipsa quae ab illo inventore veritatis et quasi architecto beatae vitae dicta sunt explicabo.","subtitle":["Test Article Subtitle"],"language":["en"],"subject":["Science","New Technology","Medicine"],"identifier":[{"type":"doi","id":"55.aa/base.1"},{"type":"publisher-id","id":"pub-15-51689"}]},"publication_date":{"publication_format":"electronic","date":"2015-01-05","year":"2015","month":"01","day":"05","season":""},"embargo":{"start":"","end":"2015-07-05","duration":"180"},"author":[{"type":"corresp","organisation_name":"Grottage Labs","name":{"firstname":"Richard","surname":"Jones","fullname":"Richard Jones","suffix":""},"identifier":[{"type":"orcid","id":"3333-0000-1111-2222"},{"type":"email","id":"richard@example.com"}],"affiliations":[{"org":"Cottage Labs org","dept":"Moonshine dept","street":"Lame street","city":"Cardiff","state":"Gwent","postcode":"HP3 9AA","country":"England","country_code":"GB","raw":"Cottage Labs org, Moonshine dept, Lame street, Cardiff, Gwent, HP3 9AA, England, ISNI: isni 1111 2222 3333, ROR: ror-123","identifier":[{"type":"ISNI","id":"isni 1111 2222 3333"},{"type":"ROR","id":"ror-123"}]}]},{"type":"author","organisation_name":"","name":{"firstname":"Mark","surname":"MacGillivray","fullname":"Mark MacGillivray"},"identifier":[{"type":"orcid","id":"1111-2222-3333-0000"},{"type":"email","id":"mark@example.com"}],"affiliations":[{"raw":"Cottage Labs, EH9 5TP"}]},{"type":"author","name":{"firstname":"Kuan-Meng","surname":"Soo","fullname":"Soo, Kuan-Meng"},"identifier":[{"type":"orcid","id":"0000-0001-7744-0424"}],"affiliations":[{"raw":"Department of Microbiology and Parasitology, Faculty of Medicine and Health Sciences, Universiti Putra Malaysia, Serdang, Selangor, Malaysia"}]},{"type":"author","organisation_name":"Author organisation only (no name)","affiliations":[{"raw":"Org name only"}]}],"contributor":[{"type":"editor","organisation_name":"ACME Org Name","name":{"firstname":"Manolo","surname":"Williams","fullname":"Manolo Williams"},"identifier":[{"type":"email","id":"manolo@example.com"}],"affiliations":[{"raw":"Lalala Labs, BS1 8HD"}]},{"type":"reviewer","organisation_name":"Contributor organisation only","identifier":[{"type":"email","id":"contrib-org@example.com"}],"affiliations":[{"raw":"Lalalalala Labs, BS1 8HD"}]}],"funding":[{"name":"Ministry of Higher Education, Malaysia","identifier":[{"type":"funder-id","id":"http://dx.doi.org/10.13039/501100003093"}],"grant_numbers":["LR001/2011A"]},{"name":"Rotary Club of Eureka","identifier":[{"type":"ringgold","id":"rot-club-eurek"},{"type":"Fundref","id":"10.13039/100008650"}],"grant_numbers":["BB/34/juwef","BB/35/juwef"]}],"license_ref":[{"title":"This is an open access article distributed in accordance with the Creative Commons Attribution 4.0 Unported (CC BY 4.0) license, which permits others to copy, redistribute, remix, transform and build upon this work for any purpose, provided the original work is properly cited, a link to the licence is given, and indication of whether changes were made. See: https://creativecommons.org/licenses/by/4.0/.","type":"open-access","url":"https://creativecommons.org/licenses/by/4.0/","version":"4.0","start":"2015-07-05"},{"title":"licence title","type":"restricted","url":"http://license-url","version":"1","start":"2022-01-02"}]},"provider":{}}'),
                (13, datetime.datetime(2023, 8, 25, 17, 15, 3), 'R', datetime.datetime(2023, 8, 25, 17, 15, 3),
                 '55.aa/base.1', 8, None, 'Wiley Fox', 'ftp', 1, '2', 'https://pubrouter.jisc.ac.uk/FilesAndJATS',
                 '[{"type":"splash","format":"text/html","url":"http://external_domain.com/some/url","access":"public"},{"type":"fulltext","format":"application/pdf","access":"router","cloc":"testfile.pdf"},{"type":"package","format":"application/zip","access":"router","packaging":"http://purl.org/net/sword/package/SimpleZip","cloc":"ArticleFilesJATS.zip"},{"type":"package","format":"application/zip","access":"router","packaging":"https://pubrouter.jisc.ac.uk/FilesAndJATS","cloc":""}]',
                 None,
                 '{"event":"publication","vers":"4","content":{},"metadata":{"publication_status":"Published","accepted_date":"2014-09-01","peer_reviewed":true,"ack":"Some acknowledgement text","journal":{"title":"Journal of Important Things","abbrev_title":"Abbreviated version of journal  title","volume":"Volume-number","issue":"Issue-number","publisher":["Premier Publisher"],"identifier":[{"type":"issn","id":"1234-5678"},{"type":"eissn","id":"1234-5678"},{"type":"pissn","id":"9876-5432"},{"type":"doi","id":"10.pp/jit"}]},"article":{"title":"Test Article","type":"research-article","version":"AAM","start_page":"Start-pg","end_page":"End-pg","page_range":"Page-range","num_pages":"Total-pages","e_num":"e-Location","abstract":"Abstract of the work. Sed ut perspiciatis unde omnis iste natus error sit voluptatem accusantium doloremque laudantium, totam rem aperiam, eaque ipsa quae ab illo inventore veritatis et quasi architecto beatae vitae dicta sunt explicabo.","subtitle":["Test Article Subtitle"],"language":["en"],"subject":["Science","New Technology","Medicine"],"identifier":[{"type":"doi","id":"55.aa/base.1"},{"type":"publisher-id","id":"pub-15-51689"}]},"publication_date":{"publication_format":"electronic","date":"2015-01-05","year":"2015","month":"01","day":"05","season":""},"embargo":{"start":"","end":"2015-07-05","duration":"180"},"author":[{"type":"corresp","organisation_name":"Grottage Labs","name":{"firstname":"Richard","surname":"Jones","fullname":"Richard Jones","suffix":""},"identifier":[{"type":"orcid","id":"3333-0000-1111-2222"},{"type":"email","id":"richard@example.com"}],"affiliations":[{"org":"Cottage Labs org","dept":"Moonshine dept","street":"Lame street","city":"Cardiff","state":"Gwent","postcode":"HP3 9AA","country":"England","country_code":"GB","raw":"Cottage Labs org, Moonshine dept, Lame street, Cardiff, Gwent, HP3 9AA, England, ISNI: isni 1111 2222 3333, ROR: ror-123","identifier":[{"type":"ISNI","id":"isni 1111 2222 3333"},{"type":"ROR","id":"ror-123"}]}]},{"type":"author","organisation_name":"","name":{"firstname":"Mark","surname":"MacGillivray","fullname":"Mark MacGillivray"},"identifier":[{"type":"orcid","id":"1111-2222-3333-0000"},{"type":"email","id":"mark@example.com"}],"affiliations":[{"raw":"Cottage Labs, EH9 5TP"}]},{"type":"author","name":{"firstname":"Kuan-Meng","surname":"Soo","fullname":"Soo, Kuan-Meng"},"identifier":[{"type":"orcid","id":"0000-0001-7744-0424"}],"affiliations":[{"raw":"Department of Microbiology and Parasitology, Faculty of Medicine and Health Sciences, Universiti Putra Malaysia, Serdang, Selangor, Malaysia"}]},{"type":"author","organisation_name":"Author organisation only (no name)","affiliations":[{"raw":"Org name only"}]}],"contributor":[{"type":"editor","organisation_name":"ACME Org Name","name":{"firstname":"Manolo","surname":"Williams","fullname":"Manolo Williams"},"identifier":[{"type":"email","id":"manolo@example.com"}],"affiliations":[{"raw":"Lalala Labs, BS1 8HD"}]},{"type":"reviewer","organisation_name":"Contributor organisation only","identifier":[{"type":"email","id":"contrib-org@example.com"}],"affiliations":[{"raw":"Lalalalala Labs, BS1 8HD"}]}],"funding":[{"name":"Ministry of Higher Education, Malaysia","identifier":[{"type":"funder-id","id":"http://dx.doi.org/10.13039/501100003093"}],"grant_numbers":["LR001/2011A"]},{"name":"Rotary Club of Eureka","identifier":[{"type":"ringgold","id":"rot-club-eurek"},{"type":"Fundref","id":"10.13039/100008650"}],"grant_numbers":["BB/34/juwef","BB/35/juwef"]}],"license_ref":[{"title":"This is an open access article distributed in accordance with the Creative Commons Attribution 4.0 Unported (CC BY 4.0) license, which permits others to copy, redistribute, remix, transform and build upon this work for any purpose, provided the original work is properly cited, a link to the licence is given, and indication of whether changes were made. See: https://creativecommons.org/licenses/by/4.0/.","type":"open-access","url":"https://creativecommons.org/licenses/by/4.0/","version":"4.0","start":"2015-07-05"},{"title":"licence title","type":"restricted","url":"http://license-url","version":"1","start":"2022-01-02"}]},"provider":{}}'),
                (14, datetime.datetime(2023, 8, 25, 17, 15, 3), 'R', datetime.datetime(2023, 8, 25, 17, 15, 3),
                 '55.aa/base.1', 8, None, 'Wiley Fox', 'ftp', 1, '2', 'https://pubrouter.jisc.ac.uk/FilesAndJATS',
                 '[{"type":"splash","format":"text/html","url":"http://external_domain.com/some/url","access":"public"},{"type":"fulltext","format":"application/pdf","access":"router","cloc":"testfile.pdf"},{"type":"package","format":"application/zip","access":"router","packaging":"http://purl.org/net/sword/package/SimpleZip","cloc":"ArticleFilesJATS.zip"},{"type":"package","format":"application/zip","access":"router","packaging":"https://pubrouter.jisc.ac.uk/FilesAndJATS","cloc":""}]',
                 None,
                 '{"event":"publication","vers":"4","content":{},"metadata":{"publication_status":"Published","accepted_date":"2014-09-01","peer_reviewed":true,"ack":"Some acknowledgement text","journal":{"title":"Journal of Important Things","abbrev_title":"Abbreviated version of journal  title","volume":"Volume-number","issue":"Issue-number","publisher":["Premier Publisher"],"identifier":[{"type":"issn","id":"1234-5678"},{"type":"eissn","id":"1234-5678"},{"type":"pissn","id":"9876-5432"},{"type":"doi","id":"10.pp/jit"}]},"article":{"title":"Test Article","type":"research-article","version":"AAM","start_page":"Start-pg","end_page":"End-pg","page_range":"Page-range","num_pages":"Total-pages","e_num":"e-Location","abstract":"Abstract of the work. Sed ut perspiciatis unde omnis iste natus error sit voluptatem accusantium doloremque laudantium, totam rem aperiam, eaque ipsa quae ab illo inventore veritatis et quasi architecto beatae vitae dicta sunt explicabo.","subtitle":["Test Article Subtitle"],"language":["en"],"subject":["Science","New Technology","Medicine"],"identifier":[{"type":"doi","id":"55.aa/base.1"},{"type":"publisher-id","id":"pub-15-51689"}]},"publication_date":{"publication_format":"electronic","date":"2015-01-05","year":"2015","month":"01","day":"05","season":""},"embargo":{"start":"","end":"2015-07-05","duration":"180"},"author":[{"type":"corresp","organisation_name":"Grottage Labs","name":{"firstname":"Richard","surname":"Jones","fullname":"Richard Jones","suffix":""},"identifier":[{"type":"orcid","id":"3333-0000-1111-2222"},{"type":"email","id":"richard@example.com"}],"affiliations":[{"org":"Cottage Labs org","dept":"Moonshine dept","street":"Lame street","city":"Cardiff","state":"Gwent","postcode":"HP3 9AA","country":"England","country_code":"GB","raw":"Cottage Labs org, Moonshine dept, Lame street, Cardiff, Gwent, HP3 9AA, England, ISNI: isni 1111 2222 3333, ROR: ror-123","identifier":[{"type":"ISNI","id":"isni 1111 2222 3333"},{"type":"ROR","id":"ror-123"}]}]},{"type":"author","organisation_name":"","name":{"firstname":"Mark","surname":"MacGillivray","fullname":"Mark MacGillivray"},"identifier":[{"type":"orcid","id":"1111-2222-3333-0000"},{"type":"email","id":"mark@example.com"}],"affiliations":[{"raw":"Cottage Labs, EH9 5TP"}]},{"type":"author","name":{"firstname":"Kuan-Meng","surname":"Soo","fullname":"Soo, Kuan-Meng"},"identifier":[{"type":"orcid","id":"0000-0001-7744-0424"}],"affiliations":[{"raw":"Department of Microbiology and Parasitology, Faculty of Medicine and Health Sciences, Universiti Putra Malaysia, Serdang, Selangor, Malaysia"}]},{"type":"author","organisation_name":"Author organisation only (no name)","affiliations":[{"raw":"Org name only"}]}],"contributor":[{"type":"editor","organisation_name":"ACME Org Name","name":{"firstname":"Manolo","surname":"Williams","fullname":"Manolo Williams"},"identifier":[{"type":"email","id":"manolo@example.com"}],"affiliations":[{"raw":"Lalala Labs, BS1 8HD"}]},{"type":"reviewer","organisation_name":"Contributor organisation only","identifier":[{"type":"email","id":"contrib-org@example.com"}],"affiliations":[{"raw":"Lalalalala Labs, BS1 8HD"}]}],"funding":[{"name":"Ministry of Higher Education, Malaysia","identifier":[{"type":"funder-id","id":"http://dx.doi.org/10.13039/501100003093"}],"grant_numbers":["LR001/2011A"]},{"name":"Rotary Club of Eureka","identifier":[{"type":"ringgold","id":"rot-club-eurek"},{"type":"Fundref","id":"10.13039/100008650"}],"grant_numbers":["BB/34/juwef","BB/35/juwef"]}],"license_ref":[{"title":"This is an open access article distributed in accordance with the Creative Commons Attribution 4.0 Unported (CC BY 4.0) license, which permits others to copy, redistribute, remix, transform and build upon this work for any purpose, provided the original work is properly cited, a link to the licence is given, and indication of whether changes were made. See: https://creativecommons.org/licenses/by/4.0/.","type":"open-access","url":"https://creativecommons.org/licenses/by/4.0/","version":"4.0","start":"2015-07-05"},{"title":"licence title","type":"restricted","url":"http://license-url","version":"1","start":"2022-01-02"}]},"provider":{}}'),
                (15, datetime.datetime(2023, 8, 25, 17, 15, 3), 'R', datetime.datetime(2023, 8, 25, 17, 15, 3),
                 '55.aa/base.1', 8, None, 'Wiley Fox', 'ftp', 1, '2', 'https://pubrouter.jisc.ac.uk/FilesAndJATS',
                 '[{"type":"splash","format":"text/html","url":"http://external_domain.com/some/url","access":"public"},{"type":"fulltext","format":"application/pdf","access":"router","cloc":"testfile.pdf"},{"type":"package","format":"application/zip","access":"router","packaging":"http://purl.org/net/sword/package/SimpleZip","cloc":"ArticleFilesJATS.zip"},{"type":"package","format":"application/zip","access":"router","packaging":"https://pubrouter.jisc.ac.uk/FilesAndJATS","cloc":""}]',
                 None,
                 '{"event":"publication","vers":"4","content":{},"metadata":{"publication_status":"Published","accepted_date":"2014-09-01","peer_reviewed":true,"ack":"Some acknowledgement text","journal":{"title":"Journal of Important Things","abbrev_title":"Abbreviated version of journal  title","volume":"Volume-number","issue":"Issue-number","publisher":["Premier Publisher"],"identifier":[{"type":"issn","id":"1234-5678"},{"type":"eissn","id":"1234-5678"},{"type":"pissn","id":"9876-5432"},{"type":"doi","id":"10.pp/jit"}]},"article":{"title":"Test Article","type":"research-article","version":"AAM","start_page":"Start-pg","end_page":"End-pg","page_range":"Page-range","num_pages":"Total-pages","e_num":"e-Location","abstract":"Abstract of the work. Sed ut perspiciatis unde omnis iste natus error sit voluptatem accusantium doloremque laudantium, totam rem aperiam, eaque ipsa quae ab illo inventore veritatis et quasi architecto beatae vitae dicta sunt explicabo.","subtitle":["Test Article Subtitle"],"language":["en"],"subject":["Science","New Technology","Medicine"],"identifier":[{"type":"doi","id":"55.aa/base.1"},{"type":"publisher-id","id":"pub-15-51689"}]},"publication_date":{"publication_format":"electronic","date":"2015-01-05","year":"2015","month":"01","day":"05","season":""},"embargo":{"start":"","end":"2015-07-05","duration":"180"},"author":[{"type":"corresp","organisation_name":"Grottage Labs","name":{"firstname":"Richard","surname":"Jones","fullname":"Richard Jones","suffix":""},"identifier":[{"type":"orcid","id":"3333-0000-1111-2222"},{"type":"email","id":"richard@example.com"}],"affiliations":[{"org":"Cottage Labs org","dept":"Moonshine dept","street":"Lame street","city":"Cardiff","state":"Gwent","postcode":"HP3 9AA","country":"England","country_code":"GB","raw":"Cottage Labs org, Moonshine dept, Lame street, Cardiff, Gwent, HP3 9AA, England, ISNI: isni 1111 2222 3333, ROR: ror-123","identifier":[{"type":"ISNI","id":"isni 1111 2222 3333"},{"type":"ROR","id":"ror-123"}]}]},{"type":"author","organisation_name":"","name":{"firstname":"Mark","surname":"MacGillivray","fullname":"Mark MacGillivray"},"identifier":[{"type":"orcid","id":"1111-2222-3333-0000"},{"type":"email","id":"mark@example.com"}],"affiliations":[{"raw":"Cottage Labs, EH9 5TP"}]},{"type":"author","name":{"firstname":"Kuan-Meng","surname":"Soo","fullname":"Soo, Kuan-Meng"},"identifier":[{"type":"orcid","id":"0000-0001-7744-0424"}],"affiliations":[{"raw":"Department of Microbiology and Parasitology, Faculty of Medicine and Health Sciences, Universiti Putra Malaysia, Serdang, Selangor, Malaysia"}]},{"type":"author","organisation_name":"Author organisation only (no name)","affiliations":[{"raw":"Org name only"}]}],"contributor":[{"type":"editor","organisation_name":"ACME Org Name","name":{"firstname":"Manolo","surname":"Williams","fullname":"Manolo Williams"},"identifier":[{"type":"email","id":"manolo@example.com"}],"affiliations":[{"raw":"Lalala Labs, BS1 8HD"}]},{"type":"reviewer","organisation_name":"Contributor organisation only","identifier":[{"type":"email","id":"contrib-org@example.com"}],"affiliations":[{"raw":"Lalalalala Labs, BS1 8HD"}]}],"funding":[{"name":"Ministry of Higher Education, Malaysia","identifier":[{"type":"funder-id","id":"http://dx.doi.org/10.13039/501100003093"}],"grant_numbers":["LR001/2011A"]},{"name":"Rotary Club of Eureka","identifier":[{"type":"ringgold","id":"rot-club-eurek"},{"type":"Fundref","id":"10.13039/100008650"}],"grant_numbers":["BB/34/juwef","BB/35/juwef"]}],"license_ref":[{"title":"This is an open access article distributed in accordance with the Creative Commons Attribution 4.0 Unported (CC BY 4.0) license, which permits others to copy, redistribute, remix, transform and build upon this work for any purpose, provided the original work is properly cited, a link to the licence is given, and indication of whether changes were made. See: https://creativecommons.org/licenses/by/4.0/.","type":"open-access","url":"https://creativecommons.org/licenses/by/4.0/","version":"4.0","start":"2015-07-05"},{"title":"licence title","type":"restricted","url":"http://license-url","version":"1","start":"2022-01-02"}]},"provider":{}}'),

            ],

            # Last tranche (for Ac with Id 2) - no more records for 1st account - notification scroller should exit normally
            [],

            ## Notifications for 2nd account (with Id 3)
            # 1st tranche - just 5 records
            [
                (101, datetime.datetime(2023, 8, 25, 17, 15, 3), 'R', datetime.datetime(2023, 8, 25, 17, 15, 3),
                 '55.aa/base.1', 8, None, 'Wiley Fox', 'ftp', 1, '3', 'https://pubrouter.jisc.ac.uk/FilesAndJATS',
                 '[{"type":"splash","format":"text/html","url":"http://external_domain.com/some/url","access":"public"},{"type":"fulltext","format":"application/pdf","access":"router","cloc":"testfile.pdf"},{"type":"package","format":"application/zip","access":"router","packaging":"http://purl.org/net/sword/package/SimpleZip","cloc":"ArticleFilesJATS.zip"},{"type":"package","format":"application/zip","access":"router","packaging":"https://pubrouter.jisc.ac.uk/FilesAndJATS","cloc":""}]',
                 None,
                 '{"event":"publication","vers":"4","content":{},"metadata":{"publication_status":"Published","accepted_date":"2014-09-01","peer_reviewed":true,"ack":"Some acknowledgement text","journal":{"title":"Journal of Important Things","abbrev_title":"Abbreviated version of journal  title","volume":"Volume-number","issue":"Issue-number","publisher":["Premier Publisher"],"identifier":[{"type":"issn","id":"1234-5678"},{"type":"eissn","id":"1234-5678"},{"type":"pissn","id":"9876-5432"},{"type":"doi","id":"10.pp/jit"}]},"article":{"title":"Test Article","type":"research-article","version":"AAM","start_page":"Start-pg","end_page":"End-pg","page_range":"Page-range","num_pages":"Total-pages","e_num":"e-Location","abstract":"Abstract of the work. Sed ut perspiciatis unde omnis iste natus error sit voluptatem accusantium doloremque laudantium, totam rem aperiam, eaque ipsa quae ab illo inventore veritatis et quasi architecto beatae vitae dicta sunt explicabo.","subtitle":["Test Article Subtitle"],"language":["en"],"subject":["Science","New Technology","Medicine"],"identifier":[{"type":"doi","id":"55.aa/base.1"},{"type":"publisher-id","id":"pub-15-51689"}]},"publication_date":{"publication_format":"electronic","date":"2015-01-05","year":"2015","month":"01","day":"05","season":""},"embargo":{"start":"","end":"2015-07-05","duration":"180"},"author":[{"type":"corresp","organisation_name":"Grottage Labs","name":{"firstname":"Richard","surname":"Jones","fullname":"Richard Jones","suffix":""},"identifier":[{"type":"orcid","id":"3333-0000-1111-2222"},{"type":"email","id":"richard@example.com"}],"affiliations":[{"org":"Cottage Labs org","dept":"Moonshine dept","street":"Lame street","city":"Cardiff","state":"Gwent","postcode":"HP3 9AA","country":"England","country_code":"GB","raw":"Cottage Labs org, Moonshine dept, Lame street, Cardiff, Gwent, HP3 9AA, England, ISNI: isni 1111 2222 3333, ROR: ror-123","identifier":[{"type":"ISNI","id":"isni 1111 2222 3333"},{"type":"ROR","id":"ror-123"}]}]},{"type":"author","organisation_name":"","name":{"firstname":"Mark","surname":"MacGillivray","fullname":"Mark MacGillivray"},"identifier":[{"type":"orcid","id":"1111-2222-3333-0000"},{"type":"email","id":"mark@example.com"}],"affiliations":[{"raw":"Cottage Labs, EH9 5TP"}]},{"type":"author","name":{"firstname":"Kuan-Meng","surname":"Soo","fullname":"Soo, Kuan-Meng"},"identifier":[{"type":"orcid","id":"0000-0001-7744-0424"}],"affiliations":[{"raw":"Department of Microbiology and Parasitology, Faculty of Medicine and Health Sciences, Universiti Putra Malaysia, Serdang, Selangor, Malaysia"}]},{"type":"author","organisation_name":"Author organisation only (no name)","affiliations":[{"raw":"Org name only"}]}],"contributor":[{"type":"editor","organisation_name":"ACME Org Name","name":{"firstname":"Manolo","surname":"Williams","fullname":"Manolo Williams"},"identifier":[{"type":"email","id":"manolo@example.com"}],"affiliations":[{"raw":"Lalala Labs, BS1 8HD"}]},{"type":"reviewer","organisation_name":"Contributor organisation only","identifier":[{"type":"email","id":"contrib-org@example.com"}],"affiliations":[{"raw":"Lalalalala Labs, BS1 8HD"}]}],"funding":[{"name":"Ministry of Higher Education, Malaysia","identifier":[{"type":"funder-id","id":"http://dx.doi.org/10.13039/501100003093"}],"grant_numbers":["LR001/2011A"]},{"name":"Rotary Club of Eureka","identifier":[{"type":"ringgold","id":"rot-club-eurek"},{"type":"Fundref","id":"10.13039/100008650"}],"grant_numbers":["BB/34/juwef","BB/35/juwef"]}],"license_ref":[{"title":"This is an open access article distributed in accordance with the Creative Commons Attribution 4.0 Unported (CC BY 4.0) license, which permits others to copy, redistribute, remix, transform and build upon this work for any purpose, provided the original work is properly cited, a link to the licence is given, and indication of whether changes were made. See: https://creativecommons.org/licenses/by/4.0/.","type":"open-access","url":"https://creativecommons.org/licenses/by/4.0/","version":"4.0","start":"2015-07-05"},{"title":"licence title","type":"restricted","url":"http://license-url","version":"1","start":"2022-01-02"}]},"provider":{}}'),
                (102, datetime.datetime(2023, 8, 25, 17, 15, 3), 'R', datetime.datetime(2023, 8, 25, 17, 15, 3),
                 '55.aa/base.1', 8, None, 'Wiley Fox', 'ftp', 1, '3', 'https://pubrouter.jisc.ac.uk/FilesAndJATS',
                 '[{"type":"splash","format":"text/html","url":"http://external_domain.com/some/url","access":"public"},{"type":"fulltext","format":"application/pdf","access":"router","cloc":"testfile.pdf"},{"type":"package","format":"application/zip","access":"router","packaging":"http://purl.org/net/sword/package/SimpleZip","cloc":"ArticleFilesJATS.zip"},{"type":"package","format":"application/zip","access":"router","packaging":"https://pubrouter.jisc.ac.uk/FilesAndJATS","cloc":""}]',
                 None,
                 '{"event":"publication","vers":"4","content":{},"metadata":{"publication_status":"Published","accepted_date":"2014-09-01","peer_reviewed":true,"ack":"Some acknowledgement text","journal":{"title":"Journal of Important Things","abbrev_title":"Abbreviated version of journal  title","volume":"Volume-number","issue":"Issue-number","publisher":["Premier Publisher"],"identifier":[{"type":"issn","id":"1234-5678"},{"type":"eissn","id":"1234-5678"},{"type":"pissn","id":"9876-5432"},{"type":"doi","id":"10.pp/jit"}]},"article":{"title":"Test Article","type":"research-article","version":"AAM","start_page":"Start-pg","end_page":"End-pg","page_range":"Page-range","num_pages":"Total-pages","e_num":"e-Location","abstract":"Abstract of the work. Sed ut perspiciatis unde omnis iste natus error sit voluptatem accusantium doloremque laudantium, totam rem aperiam, eaque ipsa quae ab illo inventore veritatis et quasi architecto beatae vitae dicta sunt explicabo.","subtitle":["Test Article Subtitle"],"language":["en"],"subject":["Science","New Technology","Medicine"],"identifier":[{"type":"doi","id":"55.aa/base.1"},{"type":"publisher-id","id":"pub-15-51689"}]},"publication_date":{"publication_format":"electronic","date":"2015-01-05","year":"2015","month":"01","day":"05","season":""},"embargo":{"start":"","end":"2015-07-05","duration":"180"},"author":[{"type":"corresp","organisation_name":"Grottage Labs","name":{"firstname":"Richard","surname":"Jones","fullname":"Richard Jones","suffix":""},"identifier":[{"type":"orcid","id":"3333-0000-1111-2222"},{"type":"email","id":"richard@example.com"}],"affiliations":[{"org":"Cottage Labs org","dept":"Moonshine dept","street":"Lame street","city":"Cardiff","state":"Gwent","postcode":"HP3 9AA","country":"England","country_code":"GB","raw":"Cottage Labs org, Moonshine dept, Lame street, Cardiff, Gwent, HP3 9AA, England, ISNI: isni 1111 2222 3333, ROR: ror-123","identifier":[{"type":"ISNI","id":"isni 1111 2222 3333"},{"type":"ROR","id":"ror-123"}]}]},{"type":"author","organisation_name":"","name":{"firstname":"Mark","surname":"MacGillivray","fullname":"Mark MacGillivray"},"identifier":[{"type":"orcid","id":"1111-2222-3333-0000"},{"type":"email","id":"mark@example.com"}],"affiliations":[{"raw":"Cottage Labs, EH9 5TP"}]},{"type":"author","name":{"firstname":"Kuan-Meng","surname":"Soo","fullname":"Soo, Kuan-Meng"},"identifier":[{"type":"orcid","id":"0000-0001-7744-0424"}],"affiliations":[{"raw":"Department of Microbiology and Parasitology, Faculty of Medicine and Health Sciences, Universiti Putra Malaysia, Serdang, Selangor, Malaysia"}]},{"type":"author","organisation_name":"Author organisation only (no name)","affiliations":[{"raw":"Org name only"}]}],"contributor":[{"type":"editor","organisation_name":"ACME Org Name","name":{"firstname":"Manolo","surname":"Williams","fullname":"Manolo Williams"},"identifier":[{"type":"email","id":"manolo@example.com"}],"affiliations":[{"raw":"Lalala Labs, BS1 8HD"}]},{"type":"reviewer","organisation_name":"Contributor organisation only","identifier":[{"type":"email","id":"contrib-org@example.com"}],"affiliations":[{"raw":"Lalalalala Labs, BS1 8HD"}]}],"funding":[{"name":"Ministry of Higher Education, Malaysia","identifier":[{"type":"funder-id","id":"http://dx.doi.org/10.13039/501100003093"}],"grant_numbers":["LR001/2011A"]},{"name":"Rotary Club of Eureka","identifier":[{"type":"ringgold","id":"rot-club-eurek"},{"type":"Fundref","id":"10.13039/100008650"}],"grant_numbers":["BB/34/juwef","BB/35/juwef"]}],"license_ref":[{"title":"This is an open access article distributed in accordance with the Creative Commons Attribution 4.0 Unported (CC BY 4.0) license, which permits others to copy, redistribute, remix, transform and build upon this work for any purpose, provided the original work is properly cited, a link to the licence is given, and indication of whether changes were made. See: https://creativecommons.org/licenses/by/4.0/.","type":"open-access","url":"https://creativecommons.org/licenses/by/4.0/","version":"4.0","start":"2015-07-05"},{"title":"licence title","type":"restricted","url":"http://license-url","version":"1","start":"2022-01-02"}]},"provider":{}}'),
                (103, datetime.datetime(2023, 8, 25, 17, 15, 3), 'R', datetime.datetime(2023, 8, 25, 17, 15, 3),
                 '55.aa/base.1', 8, None, 'Wiley Fox', 'ftp', 1, '3', 'https://pubrouter.jisc.ac.uk/FilesAndJATS',
                 '[{"type":"splash","format":"text/html","url":"http://external_domain.com/some/url","access":"public"},{"type":"fulltext","format":"application/pdf","access":"router","cloc":"testfile.pdf"},{"type":"package","format":"application/zip","access":"router","packaging":"http://purl.org/net/sword/package/SimpleZip","cloc":"ArticleFilesJATS.zip"},{"type":"package","format":"application/zip","access":"router","packaging":"https://pubrouter.jisc.ac.uk/FilesAndJATS","cloc":""}]',
                 None,
                 '{"event":"publication","vers":"4","content":{},"metadata":{"publication_status":"Published","accepted_date":"2014-09-01","peer_reviewed":true,"ack":"Some acknowledgement text","journal":{"title":"Journal of Important Things","abbrev_title":"Abbreviated version of journal  title","volume":"Volume-number","issue":"Issue-number","publisher":["Premier Publisher"],"identifier":[{"type":"issn","id":"1234-5678"},{"type":"eissn","id":"1234-5678"},{"type":"pissn","id":"9876-5432"},{"type":"doi","id":"10.pp/jit"}]},"article":{"title":"Test Article","type":"research-article","version":"AAM","start_page":"Start-pg","end_page":"End-pg","page_range":"Page-range","num_pages":"Total-pages","e_num":"e-Location","abstract":"Abstract of the work. Sed ut perspiciatis unde omnis iste natus error sit voluptatem accusantium doloremque laudantium, totam rem aperiam, eaque ipsa quae ab illo inventore veritatis et quasi architecto beatae vitae dicta sunt explicabo.","subtitle":["Test Article Subtitle"],"language":["en"],"subject":["Science","New Technology","Medicine"],"identifier":[{"type":"doi","id":"55.aa/base.1"},{"type":"publisher-id","id":"pub-15-51689"}]},"publication_date":{"publication_format":"electronic","date":"2015-01-05","year":"2015","month":"01","day":"05","season":""},"embargo":{"start":"","end":"2015-07-05","duration":"180"},"author":[{"type":"corresp","organisation_name":"Grottage Labs","name":{"firstname":"Richard","surname":"Jones","fullname":"Richard Jones","suffix":""},"identifier":[{"type":"orcid","id":"3333-0000-1111-2222"},{"type":"email","id":"richard@example.com"}],"affiliations":[{"org":"Cottage Labs org","dept":"Moonshine dept","street":"Lame street","city":"Cardiff","state":"Gwent","postcode":"HP3 9AA","country":"England","country_code":"GB","raw":"Cottage Labs org, Moonshine dept, Lame street, Cardiff, Gwent, HP3 9AA, England, ISNI: isni 1111 2222 3333, ROR: ror-123","identifier":[{"type":"ISNI","id":"isni 1111 2222 3333"},{"type":"ROR","id":"ror-123"}]}]},{"type":"author","organisation_name":"","name":{"firstname":"Mark","surname":"MacGillivray","fullname":"Mark MacGillivray"},"identifier":[{"type":"orcid","id":"1111-2222-3333-0000"},{"type":"email","id":"mark@example.com"}],"affiliations":[{"raw":"Cottage Labs, EH9 5TP"}]},{"type":"author","name":{"firstname":"Kuan-Meng","surname":"Soo","fullname":"Soo, Kuan-Meng"},"identifier":[{"type":"orcid","id":"0000-0001-7744-0424"}],"affiliations":[{"raw":"Department of Microbiology and Parasitology, Faculty of Medicine and Health Sciences, Universiti Putra Malaysia, Serdang, Selangor, Malaysia"}]},{"type":"author","organisation_name":"Author organisation only (no name)","affiliations":[{"raw":"Org name only"}]}],"contributor":[{"type":"editor","organisation_name":"ACME Org Name","name":{"firstname":"Manolo","surname":"Williams","fullname":"Manolo Williams"},"identifier":[{"type":"email","id":"manolo@example.com"}],"affiliations":[{"raw":"Lalala Labs, BS1 8HD"}]},{"type":"reviewer","organisation_name":"Contributor organisation only","identifier":[{"type":"email","id":"contrib-org@example.com"}],"affiliations":[{"raw":"Lalalalala Labs, BS1 8HD"}]}],"funding":[{"name":"Ministry of Higher Education, Malaysia","identifier":[{"type":"funder-id","id":"http://dx.doi.org/10.13039/501100003093"}],"grant_numbers":["LR001/2011A"]},{"name":"Rotary Club of Eureka","identifier":[{"type":"ringgold","id":"rot-club-eurek"},{"type":"Fundref","id":"10.13039/100008650"}],"grant_numbers":["BB/34/juwef","BB/35/juwef"]}],"license_ref":[{"title":"This is an open access article distributed in accordance with the Creative Commons Attribution 4.0 Unported (CC BY 4.0) license, which permits others to copy, redistribute, remix, transform and build upon this work for any purpose, provided the original work is properly cited, a link to the licence is given, and indication of whether changes were made. See: https://creativecommons.org/licenses/by/4.0/.","type":"open-access","url":"https://creativecommons.org/licenses/by/4.0/","version":"4.0","start":"2015-07-05"},{"title":"licence title","type":"restricted","url":"http://license-url","version":"1","start":"2022-01-02"}]},"provider":{}}'),
                (104, datetime.datetime(2023, 8, 25, 17, 15, 3), 'R', datetime.datetime(2023, 8, 25, 17, 15, 3),
                 '55.aa/base.1', 8, None, 'Wiley Fox', 'ftp', 1, '3', 'https://pubrouter.jisc.ac.uk/FilesAndJATS',
                 '[{"type":"splash","format":"text/html","url":"http://external_domain.com/some/url","access":"public"},{"type":"fulltext","format":"application/pdf","access":"router","cloc":"testfile.pdf"},{"type":"package","format":"application/zip","access":"router","packaging":"http://purl.org/net/sword/package/SimpleZip","cloc":"ArticleFilesJATS.zip"},{"type":"package","format":"application/zip","access":"router","packaging":"https://pubrouter.jisc.ac.uk/FilesAndJATS","cloc":""}]',
                 None,
                 '{"event":"publication","vers":"4","content":{},"metadata":{"publication_status":"Published","accepted_date":"2014-09-01","peer_reviewed":true,"ack":"Some acknowledgement text","journal":{"title":"Journal of Important Things","abbrev_title":"Abbreviated version of journal  title","volume":"Volume-number","issue":"Issue-number","publisher":["Premier Publisher"],"identifier":[{"type":"issn","id":"1234-5678"},{"type":"eissn","id":"1234-5678"},{"type":"pissn","id":"9876-5432"},{"type":"doi","id":"10.pp/jit"}]},"article":{"title":"Test Article","type":"research-article","version":"AAM","start_page":"Start-pg","end_page":"End-pg","page_range":"Page-range","num_pages":"Total-pages","e_num":"e-Location","abstract":"Abstract of the work. Sed ut perspiciatis unde omnis iste natus error sit voluptatem accusantium doloremque laudantium, totam rem aperiam, eaque ipsa quae ab illo inventore veritatis et quasi architecto beatae vitae dicta sunt explicabo.","subtitle":["Test Article Subtitle"],"language":["en"],"subject":["Science","New Technology","Medicine"],"identifier":[{"type":"doi","id":"55.aa/base.1"},{"type":"publisher-id","id":"pub-15-51689"}]},"publication_date":{"publication_format":"electronic","date":"2015-01-05","year":"2015","month":"01","day":"05","season":""},"embargo":{"start":"","end":"2015-07-05","duration":"180"},"author":[{"type":"corresp","organisation_name":"Grottage Labs","name":{"firstname":"Richard","surname":"Jones","fullname":"Richard Jones","suffix":""},"identifier":[{"type":"orcid","id":"3333-0000-1111-2222"},{"type":"email","id":"richard@example.com"}],"affiliations":[{"org":"Cottage Labs org","dept":"Moonshine dept","street":"Lame street","city":"Cardiff","state":"Gwent","postcode":"HP3 9AA","country":"England","country_code":"GB","raw":"Cottage Labs org, Moonshine dept, Lame street, Cardiff, Gwent, HP3 9AA, England, ISNI: isni 1111 2222 3333, ROR: ror-123","identifier":[{"type":"ISNI","id":"isni 1111 2222 3333"},{"type":"ROR","id":"ror-123"}]}]},{"type":"author","organisation_name":"","name":{"firstname":"Mark","surname":"MacGillivray","fullname":"Mark MacGillivray"},"identifier":[{"type":"orcid","id":"1111-2222-3333-0000"},{"type":"email","id":"mark@example.com"}],"affiliations":[{"raw":"Cottage Labs, EH9 5TP"}]},{"type":"author","name":{"firstname":"Kuan-Meng","surname":"Soo","fullname":"Soo, Kuan-Meng"},"identifier":[{"type":"orcid","id":"0000-0001-7744-0424"}],"affiliations":[{"raw":"Department of Microbiology and Parasitology, Faculty of Medicine and Health Sciences, Universiti Putra Malaysia, Serdang, Selangor, Malaysia"}]},{"type":"author","organisation_name":"Author organisation only (no name)","affiliations":[{"raw":"Org name only"}]}],"contributor":[{"type":"editor","organisation_name":"ACME Org Name","name":{"firstname":"Manolo","surname":"Williams","fullname":"Manolo Williams"},"identifier":[{"type":"email","id":"manolo@example.com"}],"affiliations":[{"raw":"Lalala Labs, BS1 8HD"}]},{"type":"reviewer","organisation_name":"Contributor organisation only","identifier":[{"type":"email","id":"contrib-org@example.com"}],"affiliations":[{"raw":"Lalalalala Labs, BS1 8HD"}]}],"funding":[{"name":"Ministry of Higher Education, Malaysia","identifier":[{"type":"funder-id","id":"http://dx.doi.org/10.13039/501100003093"}],"grant_numbers":["LR001/2011A"]},{"name":"Rotary Club of Eureka","identifier":[{"type":"ringgold","id":"rot-club-eurek"},{"type":"Fundref","id":"10.13039/100008650"}],"grant_numbers":["BB/34/juwef","BB/35/juwef"]}],"license_ref":[{"title":"This is an open access article distributed in accordance with the Creative Commons Attribution 4.0 Unported (CC BY 4.0) license, which permits others to copy, redistribute, remix, transform and build upon this work for any purpose, provided the original work is properly cited, a link to the licence is given, and indication of whether changes were made. See: https://creativecommons.org/licenses/by/4.0/.","type":"open-access","url":"https://creativecommons.org/licenses/by/4.0/","version":"4.0","start":"2015-07-05"},{"title":"licence title","type":"restricted","url":"http://license-url","version":"1","start":"2022-01-02"}]},"provider":{}}'),
                (105, datetime.datetime(2023, 8, 25, 17, 15, 3), 'R', datetime.datetime(2023, 8, 25, 17, 15, 3),
                 '55.aa/base.1', 8, None, 'Wiley Fox', 'ftp', 1, '3', 'https://pubrouter.jisc.ac.uk/FilesAndJATS',
                 '[{"type":"splash","format":"text/html","url":"http://external_domain.com/some/url","access":"public"},{"type":"fulltext","format":"application/pdf","access":"router","cloc":"testfile.pdf"},{"type":"package","format":"application/zip","access":"router","packaging":"http://purl.org/net/sword/package/SimpleZip","cloc":"ArticleFilesJATS.zip"},{"type":"package","format":"application/zip","access":"router","packaging":"https://pubrouter.jisc.ac.uk/FilesAndJATS","cloc":""}]',
                 None,
                 '{"event":"publication","vers":"4","content":{},"metadata":{"publication_status":"Published","accepted_date":"2014-09-01","peer_reviewed":true,"ack":"Some acknowledgement text","journal":{"title":"Journal of Important Things","abbrev_title":"Abbreviated version of journal  title","volume":"Volume-number","issue":"Issue-number","publisher":["Premier Publisher"],"identifier":[{"type":"issn","id":"1234-5678"},{"type":"eissn","id":"1234-5678"},{"type":"pissn","id":"9876-5432"},{"type":"doi","id":"10.pp/jit"}]},"article":{"title":"Test Article","type":"research-article","version":"AAM","start_page":"Start-pg","end_page":"End-pg","page_range":"Page-range","num_pages":"Total-pages","e_num":"e-Location","abstract":"Abstract of the work. Sed ut perspiciatis unde omnis iste natus error sit voluptatem accusantium doloremque laudantium, totam rem aperiam, eaque ipsa quae ab illo inventore veritatis et quasi architecto beatae vitae dicta sunt explicabo.","subtitle":["Test Article Subtitle"],"language":["en"],"subject":["Science","New Technology","Medicine"],"identifier":[{"type":"doi","id":"55.aa/base.1"},{"type":"publisher-id","id":"pub-15-51689"}]},"publication_date":{"publication_format":"electronic","date":"2015-01-05","year":"2015","month":"01","day":"05","season":""},"embargo":{"start":"","end":"2015-07-05","duration":"180"},"author":[{"type":"corresp","organisation_name":"Grottage Labs","name":{"firstname":"Richard","surname":"Jones","fullname":"Richard Jones","suffix":""},"identifier":[{"type":"orcid","id":"3333-0000-1111-2222"},{"type":"email","id":"richard@example.com"}],"affiliations":[{"org":"Cottage Labs org","dept":"Moonshine dept","street":"Lame street","city":"Cardiff","state":"Gwent","postcode":"HP3 9AA","country":"England","country_code":"GB","raw":"Cottage Labs org, Moonshine dept, Lame street, Cardiff, Gwent, HP3 9AA, England, ISNI: isni 1111 2222 3333, ROR: ror-123","identifier":[{"type":"ISNI","id":"isni 1111 2222 3333"},{"type":"ROR","id":"ror-123"}]}]},{"type":"author","organisation_name":"","name":{"firstname":"Mark","surname":"MacGillivray","fullname":"Mark MacGillivray"},"identifier":[{"type":"orcid","id":"1111-2222-3333-0000"},{"type":"email","id":"mark@example.com"}],"affiliations":[{"raw":"Cottage Labs, EH9 5TP"}]},{"type":"author","name":{"firstname":"Kuan-Meng","surname":"Soo","fullname":"Soo, Kuan-Meng"},"identifier":[{"type":"orcid","id":"0000-0001-7744-0424"}],"affiliations":[{"raw":"Department of Microbiology and Parasitology, Faculty of Medicine and Health Sciences, Universiti Putra Malaysia, Serdang, Selangor, Malaysia"}]},{"type":"author","organisation_name":"Author organisation only (no name)","affiliations":[{"raw":"Org name only"}]}],"contributor":[{"type":"editor","organisation_name":"ACME Org Name","name":{"firstname":"Manolo","surname":"Williams","fullname":"Manolo Williams"},"identifier":[{"type":"email","id":"manolo@example.com"}],"affiliations":[{"raw":"Lalala Labs, BS1 8HD"}]},{"type":"reviewer","organisation_name":"Contributor organisation only","identifier":[{"type":"email","id":"contrib-org@example.com"}],"affiliations":[{"raw":"Lalalalala Labs, BS1 8HD"}]}],"funding":[{"name":"Ministry of Higher Education, Malaysia","identifier":[{"type":"funder-id","id":"http://dx.doi.org/10.13039/501100003093"}],"grant_numbers":["LR001/2011A"]},{"name":"Rotary Club of Eureka","identifier":[{"type":"ringgold","id":"rot-club-eurek"},{"type":"Fundref","id":"10.13039/100008650"}],"grant_numbers":["BB/34/juwef","BB/35/juwef"]}],"license_ref":[{"title":"This is an open access article distributed in accordance with the Creative Commons Attribution 4.0 Unported (CC BY 4.0) license, which permits others to copy, redistribute, remix, transform and build upon this work for any purpose, provided the original work is properly cited, a link to the licence is given, and indication of whether changes were made. See: https://creativecommons.org/licenses/by/4.0/.","type":"open-access","url":"https://creativecommons.org/licenses/by/4.0/","version":"4.0","start":"2015-07-05"},{"title":"licence title","type":"restricted","url":"http://license-url","version":"1","start":"2022-01-02"}]},"provider":{}}'),

            ],

            # Simulate 'Lost connection error' on 2nd read of cursor (for 2nd account) - this is not fatal
            InterfaceError("Lost connection to MySQL server", errno=-1),

            # 2nd tranche for 2nd account - just 2 records
            [
                (106, datetime.datetime(2023, 8, 25, 17, 15, 3), 'R', datetime.datetime(2023, 8, 25, 17, 15, 3),
                 '55.aa/base.1', 8, None, 'Wiley Fox', 'ftp', 1, '3', 'https://pubrouter.jisc.ac.uk/FilesAndJATS',
                 '[{"type":"splash","format":"text/html","url":"http://external_domain.com/some/url","access":"public"},{"type":"fulltext","format":"application/pdf","access":"router","cloc":"testfile.pdf"},{"type":"package","format":"application/zip","access":"router","packaging":"http://purl.org/net/sword/package/SimpleZip","cloc":"ArticleFilesJATS.zip"},{"type":"package","format":"application/zip","access":"router","packaging":"https://pubrouter.jisc.ac.uk/FilesAndJATS","cloc":""}]',
                 None,
                 '{"event":"publication","vers":"4","content":{},"metadata":{"publication_status":"Published","accepted_date":"2014-09-01","peer_reviewed":true,"ack":"Some acknowledgement text","journal":{"title":"Journal of Important Things","abbrev_title":"Abbreviated version of journal  title","volume":"Volume-number","issue":"Issue-number","publisher":["Premier Publisher"],"identifier":[{"type":"issn","id":"1234-5678"},{"type":"eissn","id":"1234-5678"},{"type":"pissn","id":"9876-5432"},{"type":"doi","id":"10.pp/jit"}]},"article":{"title":"Test Article","type":"research-article","version":"AAM","start_page":"Start-pg","end_page":"End-pg","page_range":"Page-range","num_pages":"Total-pages","e_num":"e-Location","abstract":"Abstract of the work. Sed ut perspiciatis unde omnis iste natus error sit voluptatem accusantium doloremque laudantium, totam rem aperiam, eaque ipsa quae ab illo inventore veritatis et quasi architecto beatae vitae dicta sunt explicabo.","subtitle":["Test Article Subtitle"],"language":["en"],"subject":["Science","New Technology","Medicine"],"identifier":[{"type":"doi","id":"55.aa/base.1"},{"type":"publisher-id","id":"pub-15-51689"}]},"publication_date":{"publication_format":"electronic","date":"2015-01-05","year":"2015","month":"01","day":"05","season":""},"embargo":{"start":"","end":"2015-07-05","duration":"180"},"author":[{"type":"corresp","organisation_name":"Grottage Labs","name":{"firstname":"Richard","surname":"Jones","fullname":"Richard Jones","suffix":""},"identifier":[{"type":"orcid","id":"3333-0000-1111-2222"},{"type":"email","id":"richard@example.com"}],"affiliations":[{"org":"Cottage Labs org","dept":"Moonshine dept","street":"Lame street","city":"Cardiff","state":"Gwent","postcode":"HP3 9AA","country":"England","country_code":"GB","raw":"Cottage Labs org, Moonshine dept, Lame street, Cardiff, Gwent, HP3 9AA, England, ISNI: isni 1111 2222 3333, ROR: ror-123","identifier":[{"type":"ISNI","id":"isni 1111 2222 3333"},{"type":"ROR","id":"ror-123"}]}]},{"type":"author","organisation_name":"","name":{"firstname":"Mark","surname":"MacGillivray","fullname":"Mark MacGillivray"},"identifier":[{"type":"orcid","id":"1111-2222-3333-0000"},{"type":"email","id":"mark@example.com"}],"affiliations":[{"raw":"Cottage Labs, EH9 5TP"}]},{"type":"author","name":{"firstname":"Kuan-Meng","surname":"Soo","fullname":"Soo, Kuan-Meng"},"identifier":[{"type":"orcid","id":"0000-0001-7744-0424"}],"affiliations":[{"raw":"Department of Microbiology and Parasitology, Faculty of Medicine and Health Sciences, Universiti Putra Malaysia, Serdang, Selangor, Malaysia"}]},{"type":"author","organisation_name":"Author organisation only (no name)","affiliations":[{"raw":"Org name only"}]}],"contributor":[{"type":"editor","organisation_name":"ACME Org Name","name":{"firstname":"Manolo","surname":"Williams","fullname":"Manolo Williams"},"identifier":[{"type":"email","id":"manolo@example.com"}],"affiliations":[{"raw":"Lalala Labs, BS1 8HD"}]},{"type":"reviewer","organisation_name":"Contributor organisation only","identifier":[{"type":"email","id":"contrib-org@example.com"}],"affiliations":[{"raw":"Lalalalala Labs, BS1 8HD"}]}],"funding":[{"name":"Ministry of Higher Education, Malaysia","identifier":[{"type":"funder-id","id":"http://dx.doi.org/10.13039/501100003093"}],"grant_numbers":["LR001/2011A"]},{"name":"Rotary Club of Eureka","identifier":[{"type":"ringgold","id":"rot-club-eurek"},{"type":"Fundref","id":"10.13039/100008650"}],"grant_numbers":["BB/34/juwef","BB/35/juwef"]}],"license_ref":[{"title":"This is an open access article distributed in accordance with the Creative Commons Attribution 4.0 Unported (CC BY 4.0) license, which permits others to copy, redistribute, remix, transform and build upon this work for any purpose, provided the original work is properly cited, a link to the licence is given, and indication of whether changes were made. See: https://creativecommons.org/licenses/by/4.0/.","type":"open-access","url":"https://creativecommons.org/licenses/by/4.0/","version":"4.0","start":"2015-07-05"},{"title":"licence title","type":"restricted","url":"http://license-url","version":"1","start":"2022-01-02"}]},"provider":{}}'),
                (107, datetime.datetime(2023, 8, 25, 17, 15, 3), 'R', datetime.datetime(2023, 8, 25, 17, 15, 3),
                 '55.aa/base.1', 8, None, 'Wiley Fox', 'ftp', 1, '3', 'https://pubrouter.jisc.ac.uk/FilesAndJATS',
                 '[{"type":"splash","format":"text/html","url":"http://external_domain.com/some/url","access":"public"},{"type":"fulltext","format":"application/pdf","access":"router","cloc":"testfile.pdf"},{"type":"package","format":"application/zip","access":"router","packaging":"http://purl.org/net/sword/package/SimpleZip","cloc":"ArticleFilesJATS.zip"},{"type":"package","format":"application/zip","access":"router","packaging":"https://pubrouter.jisc.ac.uk/FilesAndJATS","cloc":""}]',
                 None,
                 '{"event":"publication","vers":"4","content":{},"metadata":{"publication_status":"Published","accepted_date":"2014-09-01","peer_reviewed":true,"ack":"Some acknowledgement text","journal":{"title":"Journal of Important Things","abbrev_title":"Abbreviated version of journal  title","volume":"Volume-number","issue":"Issue-number","publisher":["Premier Publisher"],"identifier":[{"type":"issn","id":"1234-5678"},{"type":"eissn","id":"1234-5678"},{"type":"pissn","id":"9876-5432"},{"type":"doi","id":"10.pp/jit"}]},"article":{"title":"Test Article","type":"research-article","version":"AAM","start_page":"Start-pg","end_page":"End-pg","page_range":"Page-range","num_pages":"Total-pages","e_num":"e-Location","abstract":"Abstract of the work. Sed ut perspiciatis unde omnis iste natus error sit voluptatem accusantium doloremque laudantium, totam rem aperiam, eaque ipsa quae ab illo inventore veritatis et quasi architecto beatae vitae dicta sunt explicabo.","subtitle":["Test Article Subtitle"],"language":["en"],"subject":["Science","New Technology","Medicine"],"identifier":[{"type":"doi","id":"55.aa/base.1"},{"type":"publisher-id","id":"pub-15-51689"}]},"publication_date":{"publication_format":"electronic","date":"2015-01-05","year":"2015","month":"01","day":"05","season":""},"embargo":{"start":"","end":"2015-07-05","duration":"180"},"author":[{"type":"corresp","organisation_name":"Grottage Labs","name":{"firstname":"Richard","surname":"Jones","fullname":"Richard Jones","suffix":""},"identifier":[{"type":"orcid","id":"3333-0000-1111-2222"},{"type":"email","id":"richard@example.com"}],"affiliations":[{"org":"Cottage Labs org","dept":"Moonshine dept","street":"Lame street","city":"Cardiff","state":"Gwent","postcode":"HP3 9AA","country":"England","country_code":"GB","raw":"Cottage Labs org, Moonshine dept, Lame street, Cardiff, Gwent, HP3 9AA, England, ISNI: isni 1111 2222 3333, ROR: ror-123","identifier":[{"type":"ISNI","id":"isni 1111 2222 3333"},{"type":"ROR","id":"ror-123"}]}]},{"type":"author","organisation_name":"","name":{"firstname":"Mark","surname":"MacGillivray","fullname":"Mark MacGillivray"},"identifier":[{"type":"orcid","id":"1111-2222-3333-0000"},{"type":"email","id":"mark@example.com"}],"affiliations":[{"raw":"Cottage Labs, EH9 5TP"}]},{"type":"author","name":{"firstname":"Kuan-Meng","surname":"Soo","fullname":"Soo, Kuan-Meng"},"identifier":[{"type":"orcid","id":"0000-0001-7744-0424"}],"affiliations":[{"raw":"Department of Microbiology and Parasitology, Faculty of Medicine and Health Sciences, Universiti Putra Malaysia, Serdang, Selangor, Malaysia"}]},{"type":"author","organisation_name":"Author organisation only (no name)","affiliations":[{"raw":"Org name only"}]}],"contributor":[{"type":"editor","organisation_name":"ACME Org Name","name":{"firstname":"Manolo","surname":"Williams","fullname":"Manolo Williams"},"identifier":[{"type":"email","id":"manolo@example.com"}],"affiliations":[{"raw":"Lalala Labs, BS1 8HD"}]},{"type":"reviewer","organisation_name":"Contributor organisation only","identifier":[{"type":"email","id":"contrib-org@example.com"}],"affiliations":[{"raw":"Lalalalala Labs, BS1 8HD"}]}],"funding":[{"name":"Ministry of Higher Education, Malaysia","identifier":[{"type":"funder-id","id":"http://dx.doi.org/10.13039/501100003093"}],"grant_numbers":["LR001/2011A"]},{"name":"Rotary Club of Eureka","identifier":[{"type":"ringgold","id":"rot-club-eurek"},{"type":"Fundref","id":"10.13039/100008650"}],"grant_numbers":["BB/34/juwef","BB/35/juwef"]}],"license_ref":[{"title":"This is an open access article distributed in accordance with the Creative Commons Attribution 4.0 Unported (CC BY 4.0) license, which permits others to copy, redistribute, remix, transform and build upon this work for any purpose, provided the original work is properly cited, a link to the licence is given, and indication of whether changes were made. See: https://creativecommons.org/licenses/by/4.0/.","type":"open-access","url":"https://creativecommons.org/licenses/by/4.0/","version":"4.0","start":"2015-07-05"},{"title":"licence title","type":"restricted","url":"http://license-url","version":"1","start":"2022-01-02"}]},"provider":{}}'),
            ],

            # No more records for 2nd account - the notification scroller should exit normally
            []
        ]

        # This simulates scroller cursor being empty (no unread records found) each time the Scroller is re-accessed
        mock_fetchone.return_value = None

        Deposit.send_notes_to_sword_acs()

        Deposit._process_link_package_deposit = save_plpd       # Return function to normal state (remove mock func)

        # Check account #1 values
        repo_data = AccOrg.pull(acc1.id).repository_data
        self.assertEqual(15, repo_data.last_deposited_note_id)
        self.assertEqual(OKAY, repo_data.status)
        self.assertEqual(0, repo_data.retries)

        # Check account #2 values
        repo_data = AccOrg.pull(acc2.id).repository_data
        self.assertEqual(107, repo_data.last_deposited_note_id)
        self.assertEqual(OKAY, repo_data.status)
        self.assertEqual(0, repo_data.retries)


    # @patch("octopus.modules.mysql.dao.DAOCursor._cursor_exec")
    @app_decorator
    def test_11_process_account_error(self):
        # make the iterator on JPER give us mock responses
        mocker1 = MockNoteScroller(num_notes=8,
                                   note_ids=101,
                                   stop_after=2)
        RoutedNotification.routed_scroller_obj = mocker1.create_mock_note_scroller_obj()

        # set up a mock that will fail when the function is called, to trigger the account failure
        Deposit.process_notification = mock_process_notification_fail

        current_app.config["DEPOSIT_RETRY_DELAY"] = 0  # so we don't have to wait long
        current_app.config["DEPOSIT_RETRY_LIMIT"] = 3  # so we know exactly how many

        # create an account to process
        acc = AccountFactory.repo_account()

        # this should bring us to the brink of failure, but not quite over the edge
        for i in range(3):
            Deposit.process_account(acc)

        # there was no status object, so one should have been created, which we can check for suitable properties
        repo_data = AccOrg.pull(acc.id).repository_data
        self.assertEqual(PROBLEM, repo_data.status)
        self.assertIsNone(repo_data.last_deposit_date)
        self.assertIsNone(repo_data.last_deposited_note_id)
        self.assertEqual(3, repo_data.retries)
        self.assertIsNotNone(repo_data.last_tried)

        # now one final request should tip it over the edge, and it will start failing
        Deposit.process_account(acc)

        # now look for the updated status object which should be set to "failing" mode
        repo_data = AccOrg.pull(acc.id).repository_data
        self.assertEqual(FAILING, repo_data.status)
        self.assertIsNone(repo_data.last_deposit_date)
        self.assertIsNone(repo_data.last_deposited_note_id)
        self.assertEqual(0, repo_data.retries)
        self.assertIsNone(repo_data.last_tried)

    @app_decorator
    def test_12_process_account_success(self):
        # make the iterator on JPER give us mock responses
        mocker1 = MockNoteScroller(num_notes=2,
                                   note_ids=101)
        RoutedNotification.routed_scroller_obj = mocker1.create_mock_note_scroller_obj()

        # set up a mock
        Deposit.process_notification = mock_process_notification_success

        # create an account to process
        acc = AccountFactory.repo_account()

        Deposit.process_account(acc)

        # there was no status object, so one should have been created, which we can check for suitable properties
        repo_data = AccOrg.pull(acc.id).repository_data
        self.assertEqual(OKAY, repo_data.status)
        self.assertEqual("2020-03-13T17:57:19Z", repo_data.last_deposit_date)
        self.assertEqual(0, repo_data.retries)
        self.assertEqual(102, repo_data.last_deposited_note_id)
        self.assertIsNone(repo_data.last_tried)

    @app_decorator
    def test_13_broken_repository(self):
        # create an account to process
        acc = AccountFactory.repo_account()

        # create a notification
        note = NotificationFactory.routed_notification(acc.id)

        with self.assertRaises(DepositException) as exc:
            Deposit.process_notification(acc, note)
        err_msg = str(exc.exception)
        self.assertIn("Metadata deposit failed", err_msg)
        self.assertIn("HTTPConnectionPool(host='sword', port=80)", err_msg)

    @app_decorator
    def test_14_malformed_config(self):
        # create an account to process
        acc = AccountFactory.repo_account(sword_username_pwd_collection_list=["acc1", "pass1", "/id/config"])
        # create a notification
        note = NotificationFactory.routed_notification(acc.id)

        with self.assertRaises(DepositException) as exc:  # because this is what the mock does if it gets called
            Deposit.process_notification(acc, note)
        err_msg = str(exc.exception)
        self.assertIn("Metadata deposit failed", err_msg)
        self.assertIn("Invalid URL '/id/config'", err_msg)

    @app_decorator
    def test_15_best_pdf_link_and_url_to_pathname(self):
        # Of the 3 links, 2 are PDF links (with access=public, format=application/pdf), the last is best
        links = [
            {
                "access": "public",
                "format": "application/pdf",
                "type": "fulltext",
                "url": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7499734/pdf/?tool=EBI"
            },
            {
                "access": "public",
                "format": "text/html",
                "type": "fulltext",
                "url": "https://europepmc.org/articles/PMC7499734"
            },
            {  # This should be identified as the "BEST" link, as contains "?pdf"
                "access": "public",
                "format": "application/pdf",
                "type": "fulltext",
                # URL is slightly problematic in that it has trailing slash
                "url": "https://europepmc.org/articles/PMC7499734/?pdf=render"
            }
        ]
        link_pdf = RoutedNotification._select_best_external_pdf_link(links)
        self.assertEqual(links[-1]["url"], link_pdf["url"])
        filepath = Deposit._url_to_pathname(link_pdf["url"])
        self.assertEqual('a33fda868349d669d462a8fa40dae173', filepath)

        # 2 possible links, the last is best
        links = [
            {
                "access": "public",
                "format": "application/pdf",
                "type": "fulltext",
                "url": "https://madeup.gov/pmc/articles/PMC7499734/pdf?tool=EBI"
            },
            {  # This should be identified as the "BEST" link, as contains ".pdf"
                "access": "public",
                "format": "application/pdf",
                "type": "fulltext",
                # URL is slightly problematic in that it has trailing slash
                "url": "https://madeup.org/articles/PMC7499734.pdf/"
            }
        ]
        link_pdf = RoutedNotification._select_best_external_pdf_link(links)
        self.assertEqual(links[-1]["url"], link_pdf["url"])
        filepath = Deposit._url_to_pathname(link_pdf["url"])
        self.assertEqual('36b93b94eae2f9f23daa34639b0ef445', filepath)

        # None of these links is "best" (the last is "private", which rules it out) so
        # FIRST 'public' one should be used
        links = [
            {
                "access": "public",
                "format": "application/pdf",
                "type": "fulltext",
                "url": "https://europepmc.org/api/fulltextRepo?pprId=PPR630947&type=FILE&fileName=use_this_one.pdf&mimeType=application/pdf"
            },
            {
                "access": "public",
                "format": "application/pdf",
                "type": "fulltext",
                "url": "https://madeup.org/articles/PMC7499734/filename"
            },
            {
                "access": "private",
                "format": "application/pdf",
                "type": "fulltext",
                "url": "https://madeup.gov/pmc/articles/PMC7499734/file.pdf"
            }
        ]
        link_pdf = RoutedNotification._select_best_external_pdf_link(links)
        self.assertEqual(links[0]["url"], link_pdf["url"])
        filepath = Deposit._url_to_pathname(link_pdf["url"])
        self.assertEqual('10a7d0d919eef99b5e29bbc2996fe716', filepath)

        urls = [
            'https://europepmc.org/api/fulltextRepo?pprId=PPR632561&type=FILE&fileName=EMS172580-pdf.pdf&mimeType=application/pdf',
            'https://europepmc.org/api/fulltextRepo?pprId=PPR620418&type=FILE&fileName=EMS170731-pdf.pdf&mimeType=application/pdf',
            'https://europepmc.org/api/fulltextRepo?pprId=PPR594312&type=FILE&fileName=EMS159578-pdf.pdf&mimeType=application/pdf',
            'https://europepmc.org/api/fulltextRepo?pprId=PPR631269&type=FILE&fileName=EMS172492-pdf.pdf&mimeType=application/pdf',
            'https://europepmc.org/api/fulltextRepo?pprId=PPR624860&type=FILE&fileName=EMS171099-pdf.pdf&mimeType=application/pdf',
            'https://europepmc.org/api/fulltextRepo?pprId=PPR638856&type=FILE&fileName=EMS173342-pdf.pdf&mimeType=application/pdf',
            'https://europepmc.org/api/fulltextRepo?pprId=PPR594914&type=FILE&fileName=EMS160080-pdf.pdf&mimeType=application/pdf',
            'https://europepmc.org/api/fulltextRepo?pprId=PPR630677&type=FILE&fileName=EMS172491-pdf.pdf&mimeType=application/pdf',
            'https://europepmc.org/api/fulltextRepo?pprId=PPR594315&type=FILE&fileName=EMS159588-pdf.pdf&mimeType=application/pdf',
            'https://europepmc.org/api/fulltextRepo?pprId=PPR630947&type=FILE&fileName=EMS172390-pdf.pdf&mimeType=application/pdf',
            'https://europepmc.org/api/fulltextRepo?pprId=PPR609636&type=FILE&fileName=EMS163698-pdf.pdf&mimeType=application/pdf',
            'https://europepmc.org/api/fulltextRepo?pprId=PPR629249&type=FILE&fileName=EMS172289-pdf.pdf&mimeType=application/pdf',
            'https://europepmc.org/api/fulltextRepo?pprId=PPR595378&type=FILE&fileName=EMS159972-pdf.pdf&mimeType=application/pdf',
            'https://europepmc.org/api/fulltextRepo?pprId=PPR625959&type=FILE&fileName=EMS171892-pdf.pdf&mimeType=application/pdf',
            'https://europepmc.org/api/fulltextRepo?pprId=PPR619989&type=FILE&fileName=EMS170724-pdf.pdf&mimeType=application/pdf',
            'https://europepmc.org/api/fulltextRepo?pprId=PPR595926&type=FILE&fileName=EMS159825-pdf.pdf&mimeType=application/pdf',
            'https://europepmc.org/api/fulltextRepo?pprId=PPR594314&type=FILE&fileName=EMS159579-pdf.pdf&mimeType=application/pdf',
            'https://europepmc.org/api/fulltextRepo?pprId=PPR596029&type=FILE&fileName=EMS159982-pdf.pdf&mimeType=application/pdf',
            'https://europepmc.org/api/fulltextRepo?pprId=PPR595348&type=FILE&fileName=EMS160083-pdf.pdf&mimeType=application/pdf',
            'https://europepmc.org/api/fulltextRepo?pprId=PPR645675&type=FILE&fileName=EMS174335-pdf.pdf&mimeType=application/pdf',
            'https://europepmc.org/api/fulltextRepo?pprId=PPR629016&type=FILE&fileName=EMS172239-pdf.pdf&mimeType=application/pdf',
            'https://europepmc.org/api/fulltextRepo?pprId=PPR630589&type=FILE&fileName=EMS172468-pdf.pdf&mimeType=application/pdf'
        ]
        filenames = set()
        for url in urls:
            filenames.add(Deposit._url_to_pathname(url))
        # Assert no collisions (if there were, then num filenames would be less than number of urls)
        assert len(urls) == len(filenames)


    @app_decorator
    def test_16_duplicate_notification_by_email(self):
        """
        Test the following scenarios -
        Duplicate sent by email: XML format
        Duplicate sent by email: JSON format
        Duplicate sent by email: Text format
        @return:
        """
        acc = AccountFactory.repo_account(duplicates_dict={"emails": ["adam.rehin@jisc.ac.uk"], "meta_format": "xml"},
                                          repo_xml_format="eprints-rioxx")
        note = NotificationFactory.routed_notification(acc.id, duplicates=True)

        # make earlier deposit records object to record the events
        deposit_record = {
            "repo_id": acc.id,
            "note_id": 2,
            "doi": note.article_doi,
            "metadata_status": DEPOSITED,
            "content_status": DEPOSITED,
            "completed_status": DEPOSITED,
            "edit_iri": "https://some-repository-url/location/111"
        }
        deposit_rec_1 = SwordDepositRecord(deposit_record)
        deposit_rec_1.insert(reload=True)

        sleep(1)    # Ensure deposit_rec_2 has later date and is marked as failed
        deposit_record["note_id"] = 3
        deposit_record["content_status"] = None
        deposit_record["edit_iri"] ="https://some-repository-url/location/222"
        deposit_rec_2 = SwordDepositRecord(deposit_record)
        deposit_rec_2.insert(reload=True)

        # process the notification, which we expect to go without error, sent by email
        Deposit.process_notification(acc, note)
        first_deposit_date_str = dates.reformat(deposit_rec_1.deposit_date, "%Y-%m-%dT%H:%M:%SZ", "%d/%m/%Y at %H:%M:%S")
        email_text = Deposit.mail_account.last_sent
        assert "This email describes an article with DOI '55.aa/base.1' received directly from Wiley Fox which has been seen in 2 notifications previously sent to you." in email_text
        assert f"The first was sent on {first_deposit_date_str} and saved as <a href=\"https://some-repository-url/location/111\">https://some-repository-url/location/111</a>. That notification had an article file attached." in email_text
        assert "The most recent notification was sent on {} and saved as <a href=\"https://some-repository-url/location/222\">https://some-repository-url/location/222</a>. That notification had no article file (it was metadata only)".format(dates.reformat(deposit_rec_2.deposit_date, "%Y-%m-%dT%H:%M:%SZ", "%d/%m/%Y at %H:%M:%S")) in email_text
        assert '<h2>Metadata <span class="smaller">&nbsp;(Eprints RIOXX XML format)</span></h2>' in email_text

        dr = SwordDepositRecord.pull_most_recent_by_note_id_and_repo_id(note.id, acc.id)
        assert "email" == dr.edit_iri
        last_dr_deposit_date = dr.deposit_date

        ###
        ### Now change account duplicates metadata format to JSON (i.e. is what should be sent in the email)
        ### Also change first (earliest) deposit record's content status to failed --> should get different text in email
        ###
        deposit_rec_1.content_status = FAILED
        deposit_rec_1.update()

        acc.repository_data.dups_meta_format = "json"
        acc.update()
        # process the notification, which we expect to go without error, sent by email
        Deposit.process_notification(acc, note)

        email_text = Deposit.mail_account.last_sent

        ### NOTE there are now 3 previous notifications
        assert "This email describes an article with DOI '55.aa/base.1' received directly from Wiley Fox which has been seen in 3 notifications previously sent to you." in email_text
        ### Text no says that article file failed to deposit
        assert f"The first was sent on {first_deposit_date_str} and saved as <a href=\"https://some-repository-url/location/111\">https://some-repository-url/location/111</a>. That notification had an article file but it failed to deposit (so only the metadata was saved)." in email_text
        ### Most recent notification was one created by first call to process_notification, text now says it was sent by email.
        assert "The most recent notification was sent on {}/{}/{} at {} by email. That notification had an article file attached.".format(last_dr_deposit_date[8:10], last_dr_deposit_date[5:7], last_dr_deposit_date[0:4], last_dr_deposit_date[11:19]) in email_text
        assert '<h2>Metadata <span class="smaller">&nbsp;(JSON format)</span></h2>' in email_text

        ###
        ### Now output Metadata as Text (table)
        ###
        acc.repository_data.dups_meta_format = "text"
        acc.update()
        # process the notification, which we expect to go without error, sent by email
        Deposit.process_notification(acc, note)
        email_text = Deposit.mail_account.last_sent
        assert '<h2>Metadata <span class="smaller">&nbsp;(Text format)</span></h2>' in email_text
        assert '<tr class="hi"><th>Article version</th><td>AAM</td></tr>' in email_text

