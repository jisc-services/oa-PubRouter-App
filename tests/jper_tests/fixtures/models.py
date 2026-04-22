import datetime
from dateutil.relativedelta import relativedelta
from router.jper.models.jats import JATS
from router.jper.models.identifier import Identifier
from router.jper.models.publisher import FTPDepositRecord
from octopus.lib.paths import get_real_path
from uuid import uuid4



ERROR_RECORD = {
    "error": "error",
    "matched": False,
    "successful": False,
    "name": "error.zip"
}

SUCCESS_RECORD = {
    "matched": False,
    "successful": True,
    "name": "success.zip",
    "error": ""
}

MATCHED_RECORD = {
    "matched": True,
    "successful": True,
    "name": "matched.zip",
    "error": ""
}


class PubDepositRecordFactory:

    @classmethod
    def _make_ftp_record(cls, data, publisher_id=None, note_id=None, created_date=None):
        ftp_record = FTPDepositRecord(data)
        ftp_record.publisher_id = publisher_id or 999
        ftp_record.notification_id = note_id or 888
        if created_date:
            ftp_record.created = created_date
        ftp_record.insert(reload=True)
        return ftp_record

    @classmethod
    def ftp_error(cls, publisher_id=None, note_id=None, created_date=None):
        return cls._make_ftp_record(ERROR_RECORD, publisher_id, note_id, created_date)

    @classmethod
    def ftp_success(cls, publisher_id=None, note_id=None, created_date=None):
        return cls._make_ftp_record(SUCCESS_RECORD, publisher_id, note_id, created_date)

    @classmethod
    def ftp_matched(cls, publisher_id=None, note_id=None, created_date=None):
        return cls._make_ftp_record(MATCHED_RECORD, publisher_id, note_id, created_date)

    @classmethod
    def make_many_ftp_success_records(cls, publisher_id=None):
        max_date = datetime.datetime.today()
        for num in range(30):
            cls.ftp_success(publisher_id, num + 1, (max_date - relativedelta(days=num)).strftime("%Y-%m-%d"))


class JATSFactory:

    @classmethod
    def _make_jats(cls, *args):
        with open(get_real_path(__file__, "../", "resources", *args), "rb") as xml:
            return JATS(xml.read())

    @classmethod
    def jats_from_file(cls, filename):
        return cls._make_jats(filename)

    @classmethod
    def multi_license_xml(cls):
        return cls._make_jats("valid_jats_multi_license.xml")

    @classmethod
    def multi_license_xml_no_license_xlink(cls):
        return cls._make_jats("valid_jats_multi_license_no_license_href.xml")

    @classmethod
    def multi_license_xml_multiple_license_p(cls):
        return cls._make_jats("valid_jats_multi_license_p.xml")

    @classmethod
    def license_p_only_extlink_xml(cls):
        return cls._make_jats("valid_jats_only_license_p_extlink.xml")

    @classmethod
    def license_p_only_no_extlink_xml(cls):
        return cls._make_jats("valid_jats_only_license_p_no_extlink.xml")

    @classmethod
    def license_with_start_date(cls):
        return cls._make_jats("valid_jats_start_date.xml")

    @classmethod
    def jats_general(cls):
        return cls._make_jats("jats_test_file.xml")


class IdentifierFactory:
    @classmethod
    def _make_identifier(cls, type, name):
        identifier = Identifier({"type": type, "name": name, "value": uuid4().hex})
        identifier.insert()
        return identifier

    @classmethod
    def make_jisc(cls, name):
        return cls._make_identifier("JISC", name)

    @classmethod
    def make_core(cls, name):
        return cls._make_identifier("CORE", name)
