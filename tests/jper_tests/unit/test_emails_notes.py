"""
Unit tests for emails/notes handling.
Tests:
    * Functions to insert/update/retrieve records from `acc_notes_emails` table (via AccNotesEmails class)
    * `note_email_ajax` blueprint functionality in `views\account`
"""
import json
from functools import partial
from flask import url_for
from router.jper.web_main import app_decorator
from router.shared.models.account import AccNotesEmails
from tests.jper_tests.fixtures.testcase import JPERTestCase

class TestEmailsNotes(JPERTestCase):
    @classmethod
    def setUpClass(cls):
        # List the tables (by table name) needed for testing
        cls.tables_for_testing = ['account', 'acc_user', 'acc_bulk_email', 'acc_notes_emails']
        super().setUpClass()

    @app_decorator
    def setUp(self):
        super(TestEmailsNotes, self).setUp()

    @app_decorator
    def tearDown(self):
        super(TestEmailsNotes, self).tearDown()

    @app_decorator
    def login(self, username="admin", password="admin", follow_redirects=True):
        return self.test_client.post(url_for('account.login'), data={
            "username": username,
            "password": password
        }, follow_redirects=follow_redirects)

    @app_decorator
    def logout(self):
        return self.test_client.get(url_for("account.logout"), follow_redirects=True)

    @staticmethod
    def remove_keys_vals(data_dict, key_list):
        new_dict = data_dict.copy()
        for k in key_list:
            del new_dict[k]
        return new_dict

    @staticmethod
    def note_email_dict(note_or_email="N", status=None, acc_id=1, good=True, add_junk=False, append=""):
        """
        Return dictionary containing data for note or email
        :param note_or_email: String(1) - "N" (Note) or "E" (Email)
        :param status: String(1) - "H" (Highlight), "D" (Delete), None (NULL)
        :param acc_id: Integer - Id of Account record
        :param good: Boolean - True: data-dict is OK; False: data-dict has problems
        :param add_junk: Boolean - True: Add some random dict elements; False: no junk
        :param append: String - Text to append to default Subject & Message text
        :return: Dict
        """
        snippet_dict = {"N": "Note", "E": "Email"}
        ret_dict = {
            "acc_id": acc_id,
            "type": note_or_email,
            "status": status

        }
        if good:
            ret_dict["subject"] = f"{snippet_dict[note_or_email]} test subject{append}"
            ret_dict["body"] = f"This is a {snippet_dict[note_or_email]} test message{append}. Blah blah blah blah blah."
            if note_or_email == "E":
                ret_dict["to_addr"] = "to.someone@testit.com; second.person@test.ac.uk"
                ret_dict["cc_addr"] = "cc.one@testit.com; cc.two@wonky.com"
                ret_dict["err_ids"] = [111, 222, 333]
        else:
            if note_or_email == "E":
                ret_dict["to_addr"] = "BAD-ADDRESS good.address@test.ac.uk"
                ret_dict["cc_addr"] = "BAD-CC-ADDRESS good.cc.address@test.ac.uk"

        if add_junk:
            ret_dict["junk"] = "Unexpected dict value"
        return ret_dict

    @app_decorator
    def test_01_acc_notes_emails_table_insert_update_retrieve_ok(self):
        """
        Test insert_email() & insert_note() functions for inserting email & note respectively into
         `acc_notes_emails` table.
        """
        saved_note_email_recs = []
        ## 1 - Insert Email using "perfect" dict using insert_email() function
        email_dict = self.note_email_dict(note_or_email="E", acc_id=1, append=" 1A")
        orig_dict = email_dict.copy()
        saved_rec = AccNotesEmails(email_dict).insert_email()
        saved_note_email_recs.append(saved_rec)
        # remove id & created which are added upon inserting the database record
        adjusted_saved_rec = self.remove_keys_vals(saved_rec, ["id", "created", "bulk_email_id"])
        assert adjusted_saved_rec == orig_dict

        ## 2 - Insert Email using "imperfect" dict using insert_email() function - unexpected values SHOULD BE REMOVED
        email_dict = self.note_email_dict(note_or_email="E", status="H", acc_id=1, add_junk=True, append=" 1BH")
        orig_dict = email_dict.copy()
        saved_rec = AccNotesEmails(email_dict).insert_email()
        saved_note_email_recs.append(saved_rec)
        # remove id & created which are added upon inserting the database record
        adjusted_saved_rec = self.remove_keys_vals(saved_rec, ["id", "created", "bulk_email_id"])
        # The saved rec should NOT match orig_dict which contains a junk entry
        assert adjusted_saved_rec != orig_dict
        adjusted_orig_dict = self.remove_keys_vals(orig_dict, ["junk"])
        # The saved rec should match orig_dict WITHOUT the junk entry
        assert adjusted_saved_rec == adjusted_orig_dict

        ## 3 - Insert Note using "perfect" dict using insert_note() function
        note_dict = self.note_email_dict(note_or_email="N", acc_id=1, append=" 1C")
        orig_dict = note_dict.copy()
        saved_rec = AccNotesEmails(note_dict).insert_note()
        saved_note_email_recs.append(saved_rec)
        # remove id & created which are added upon inserting the database record
        adjusted_saved_rec = self.remove_keys_vals(saved_rec, ["id", "created", "bulk_email_id"])
        assert adjusted_saved_rec == orig_dict

        ## 4 - Insert Note using "imperfect" dict using  insert_note() function - unexpected values SHOULD BE REMOVED
        note_dict = self.note_email_dict(note_or_email="N", status="H", acc_id=1, add_junk=True, append=" 1DH")
        orig_dict = note_dict.copy()
        saved_rec = AccNotesEmails(note_dict).insert_note()
        saved_note_email_recs.append(saved_rec)
        # remove id & created which are added upon inserting the database record
        adjusted_saved_rec = self.remove_keys_vals(saved_rec, ["id", "created", "bulk_email_id"])
        # The saved rec should NOT match orig_dict which contains a junk entry
        assert adjusted_saved_rec != orig_dict
        adjusted_orig_dict = self.remove_keys_vals(orig_dict, ["junk"])
        # The saved rec should match orig_dict WITHOUT the junk entry
        assert adjusted_saved_rec == adjusted_orig_dict

        ## 5 Add several additional records with different account IDs
        counter = 1
        for acc_id, rec_type, status in ((2, "E", None), (2, "E", "H"), (2, "N", None), (2, "N", "H"), (2, "E", "R"),
                                         (3, "E", None), (3, "E", "H"), (3, "N", None), (3, "N", "H"), (3, "E", "R")
                                        ):
            data_dict = self.note_email_dict(note_or_email=rec_type, status=status, acc_id=acc_id, append=f" {counter}{status}")
            counter += 1
            ac_note_email = AccNotesEmails(data_dict)
            saved_rec = ac_note_email.insert_email() if rec_type == "E" else ac_note_email.insert_note()
            saved_note_email_recs.append(saved_rec)

        # We should have inserted 12 records
        assert len(saved_note_email_recs) == 14

        ## 6 Retrieve All notes/emails for Acc ID 1 - EXPECT 5 records, the first 2 should have highlighted status ("H").
        ##   because these are always returned first. Records are sorted by status & ID descending
        retrieved_recs = AccNotesEmails.list_notes_emails_todos_dicts(1)
        assert len(retrieved_recs) == 4
        assert retrieved_recs[0] == saved_note_email_recs[3]    # last highlighted record inserted
        assert retrieved_recs[1] == saved_note_email_recs[1]    # first highlighted record inserted
        assert retrieved_recs[2] == saved_note_email_recs[2]    # last non-highlighted rec inserted
        assert retrieved_recs[3] == saved_note_email_recs[0]    # first non-highlighted rec insered

        ## 7 Retrieve All Notes for Acc ID 2 - EXPECT 2 records, the first should have highlighted status ("H").
        retrieved_recs = AccNotesEmails.list_notes_emails_todos_dicts(2, rec_type="N")
        assert len(retrieved_recs) == 2
        assert retrieved_recs[0] == saved_note_email_recs[7]    # highlighted Note record inserted
        assert retrieved_recs[1] == saved_note_email_recs[6]    # un-highlighted Note highlighted record inserted

        ## 8 Retrieve All Emails for Acc ID 3 - EXPECT 3 records, the first should have highlighted status ("H").
        retrieved_recs = AccNotesEmails.list_notes_emails_todos_dicts(3, rec_type="E")
        assert len(retrieved_recs) == 3
        assert retrieved_recs[0] == saved_note_email_recs[10]  # highlighted Email record inserted
        assert retrieved_recs[1] == saved_note_email_recs[13]  # un-highlighted Email highlighted record inserted
        assert retrieved_recs[2] == saved_note_email_recs[9]  # un-highlighted Email highlighted record inserted

        ## 9 Retrieve All Emails for Acc ID 3 with Highlighted or Resolved status - EXPECT 2 records, the first should have highlighted status ("H").
        retrieved_recs = AccNotesEmails.list_notes_emails_todos_dicts(3, rec_type="E", status="HR")
        assert len(retrieved_recs) == 2
        assert retrieved_recs[0] == saved_note_email_recs[10]  # highlighted Email record inserted
        assert retrieved_recs[1] == saved_note_email_recs[13]  # un-highlighted Email highlighted record inserted

        ## 9 Retrieve All recs (Notes & Emails) for Acc ID 3 which do NOT have None (Null) status - EXPECT 3 records, the first should have highlighted status ("H").
        retrieved_recs = AccNotesEmails.list_notes_emails_todos_dicts(3, status="HDR")
        assert len(retrieved_recs) == 3
        assert retrieved_recs[0] == saved_note_email_recs[12]  # Last highlighted record inserted
        assert retrieved_recs[1] == saved_note_email_recs[10]  # First highlighted record inserted

        ## 11 Update status to highlighted for ALL saved records
        all_saved_rec_ids = [dic["id"] for dic in saved_note_email_recs]
        num_updated = AccNotesEmails.update_note_email_status(all_saved_rec_ids, "H")
        # Because 6 of the 12 saved records already have status "H", we expect only 6 to be udpated
        assert num_updated == 8
        # We expect ALL recs for Acc ID 1 to have highlighted status
        retrieved_recs = AccNotesEmails.list_notes_emails_todos_dicts(1)
        assert len(retrieved_recs) == 4
        for rec in retrieved_recs:
            assert rec["status"] == "H"

        ## 12 Update status to Deleted for ALL saved records
        num_updated = AccNotesEmails.update_note_email_status(all_saved_rec_ids, "D")
        assert num_updated == 14
        # We expect NO records to be returned when doing a default list_notes_emails_todos_dicts
        for acc_id in (1, 2, 3):
            retrieved_recs = AccNotesEmails.list_notes_emails_todos_dicts(acc_id)
            assert len(retrieved_recs) == 0
        # Now retrieve records for Acc 3, with Deleted status - EXPECT 5 recs
        retrieved_recs = AccNotesEmails.list_notes_emails_todos_dicts(3, status="D")
        assert len(retrieved_recs) == 5

    @app_decorator
    def test_02_acc_notes_emails_ajax(self):
        """
        Test note_email_ajax endpoint
        """
        self.login()
        partial_post = partial(self.test_client.post,
                               url_for("account.note_email_ajax"),
                               content_type="application/json")
        added_rec_ids = []

        ### SUCCESS CASES ###

        ## 1 - Send Email - Highlighted
        data_dict = {
            'acc_id': 1,
            'subject': 'Email test subject 1A',
            'body': 'This is a Email test message 1A. Blah blah blah blah blah.',
            'to_addr': 'to.someone@testit.com second.person@test.ac.uk',
            'cc_addr': 'cc.one@testit.com cc.two@wonky.com',
            'err_ids': [],
            'status': 'H',  # Highlight
            'func': 'send_email'
        }
        resp = partial_post(data=json.dumps(data_dict))
        assert resp.status_code == 200
        j = resp.json
        assert j["msg"] == "Email sent"
        added_rec_ids.append(j["rec"]["id"])


        ## 2 - Add Note
        data_dict = {
            'acc_id': 1,
            'subject': 'Note test subject 1A',
            'body': 'This is a Note test message 1A. Blah blah blah blah blah.',
            'func': 'save_note'
        }
        resp = partial_post(data=json.dumps(data_dict))
        assert resp.status_code == 200
        j = resp.json
        assert j["msg"] == "Note saved"
        added_rec_ids.append(j["rec"]["id"])


        ## 3 - List notes & emails - JSON should contain list of the 2 records just added above, highlighted note FIRST
        data_dict = {
            'acc_id': 1,
            'func': 'list_all_types'
        }
        resp = partial_post(data=json.dumps(data_dict))
        assert resp.status_code == 200
        j = resp.json
        assert len(j) == 2      # 2 records

        rec = j[0]
        assert rec["id"] == added_rec_ids[0]
        assert rec["type"] == "E"     # Email
        assert rec["status"] == "H"   # Highlighted

        rec = j[1]
        assert rec["id"] == added_rec_ids[1]
        assert rec["type"] == "N"     # Note
        assert rec["status"] is None  # NOT Highlighted

        #4 - Remove highlights from ALL records
        for id in added_rec_ids:
            data_dict = {
                'rec_id': id,
                'func': 'update_status',
                'status': 'N'
            }
            resp = partial_post(data=json.dumps(data_dict))
            assert resp.status_code == 200


        ## 5 - list only emails
        data_dict = {
            'acc_id': 1,
            'func': 'list_all_types',
            'rec_type': 'E'
        }
        resp = partial_post(data=json.dumps(data_dict))
        assert resp.status_code == 200
        j = resp.json
        assert len(j) == 1      # 1 records

        rec = j[0]
        assert rec["id"] == added_rec_ids[0]
        assert rec["type"] == "E"     # Email
        assert rec["status"] is None  # Highlighted status should now be unset


        ## 6 - Delete all
        for id in added_rec_ids:
            data_dict = {
                'rec_id': id,
                'func': 'update_status',
                'status': 'D'
            }
            resp = partial_post(data=json.dumps(data_dict))
            assert resp.status_code == 200
            j = resp.json
            assert j == {'msg': 'Record updated', 'recs_updated': 1}


        ## 7 - List notes & emails - Expect none to be listed
        data_dict = {
            'acc_id': 1,
            'func': 'list_all_types'
        }
        resp = partial_post(data=json.dumps(data_dict))
        assert resp.status_code == 200
        j = resp.json
        assert len(j) == 0


        ## 8 - List deleted notes & emails - Expect 2
        data_dict = {
            'acc_id': 1,
            'func': 'list_all_types',
            'rec_status': 'D'
        }
        resp = partial_post(data=json.dumps(data_dict))
        assert resp.status_code == 200
        j = resp.json
        assert len(j) == 2

        ## 9 - List deleted notes - Expect 1
        data_dict = {
            'acc_id': 1,
            'func': 'list_all_types',
            'rec_type': 'N',
            'rec_status': 'D'
        }
        resp = partial_post(data=json.dumps(data_dict))
        assert resp.status_code == 200
        j = resp.json
        assert len(j) == 1

        ### FAILURE CASES ###

        ## 10 - Create Email FAILURE - bad email address
        data_dict = {
            'acc_id': 1,
            'subject': 'Email test subject 1A',
            'body': 'This is a Email test message 1A. Blah blah blah blah blah.',
            'to_addr': 'OOPS.BAD.ADDRESS',
            'err_ids': [],
            'func': 'send_email'
        }
        resp = partial_post(data=json.dumps(data_dict))
        assert resp.status_code == 400
        j = resp.json
        assert j == {'error': "Invalid email address entered: 'OOPS.BAD.ADDRESS'"}


        ## 11 - Add Note FAILURE - Missing body field (also missing subject, but that is OK)
        data_dict = {
            'acc_id': 1,
            'func': 'save_note'
        }
        resp = partial_post(data=json.dumps(data_dict))
        assert resp.status_code == 400
        j = resp.json
        assert j == {'error': 'body field is required'}

        ## 12 - Bad function name
        data_dict = {
            'acc_id': 1,
            'func': 'bad_func'
        }
        resp = partial_post(data=json.dumps(data_dict))
        assert resp.status_code == 400
        j = resp.json
        assert j == {'error': "Function 'bad_func' missing or not recognised"}


