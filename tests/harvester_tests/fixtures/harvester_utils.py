from datetime import datetime
from copy import deepcopy
from dateutil.relativedelta import relativedelta
from flask import current_app
from octopus.modules.es.connector import ESConnection
from router.shared.models.harvester import HarvesterWebserviceModel


HARV_WS_BASE_DICT = {
    'name': "SET ME",
    'url': "SET ME",
    'query': "SET ME",
    'frequency': "daily",
    'active': True,
    'email': "test@test.com",
    'end_date': None,
    'engine': "SET ME",
    'wait_window': 1,
    'publisher': False,
    'live_date': None
}


class HarvesterTestUtils:
    """
    Also contains useful functions for initializing indexes
    Class to create Harvester webservice account records in elasticsearch database.
    """

    @staticmethod
    def test_url(engine):
         return current_app.config[f"WEBSERVICES_DATA_{engine}"]["url"]

    @staticmethod
    def test_query(engine):
         return current_app.config[f"WEBSERVICES_DATA_{engine}"]["query"]

    @staticmethod
    def es_conn():
        return ESConnection(current_app.config["ELASTIC_SEARCH_HOST"])


    @staticmethod
    def save_webservice(ws_data, webservice_id=None):
        """
        Save webservice record - either creates a new record (if webservice_id is None) or updates
        an existing record.
        :param ws_data: Simple dict of webservice data (alternative to webservice_form_dict)
        :param webservice_id: Unique ID of webservice record (if one exists)
        :return: result data dict
        """
        ws_obj = HarvesterWebserviceModel(ws_data)
        # No existing ID: Insert record
        if webservice_id is None:
            rec_dict = ws_obj.insert()
        else:
            ws_obj.id = webservice_id   # just in case not set!
            # Update webservice record
            rec_dict = ws_obj.update()
        return rec_dict

    @staticmethod
    def make_ws_dict(harvester, name_prefix="", end_date_offset=2, **kwargs):
        """
        Create a harvester webservice dict
        :param harvester: string - name of harvester in CAPS, one of: EPMC, PUBMED, CROSSREF, ELSEVIER
        :param name_prefix: string - Prefix for harvester name OPTIONAL
        :param end_date_offset: integer - number of days prior to today to set end date
        :param kwargs:  - list of key|val pairs used to set particular values of the dict
        :return: dict
        """
        ws_dict = deepcopy(HARV_WS_BASE_DICT)
        name = current_app.config[harvester]
        ws_dict['name'] =  f"{name_prefix}_{name}" if name_prefix else name
        ws_dict['url'] = HarvesterTestUtils.test_url(harvester)
        ws_dict['query'] = HarvesterTestUtils.test_query(harvester)
        end_date_obj = datetime.today() - relativedelta(days=end_date_offset)
        ws_dict['end_date'] = end_date_obj.strftime("%Y-%m-%d")
        ws_dict['engine'] = name
        for k, v in kwargs.items():
            ws_dict[k] = v
        return ws_dict


    @staticmethod
    def create_ws_record(data_dict):
        rec = HarvesterTestUtils.save_webservice(data_dict)
        return rec["id"]

    @staticmethod
    def create_test_epmc_ws_record():
        """
        Create EPMC Test harvester webservice
        :return: ID of webservice record or None
        """
        return HarvesterTestUtils.create_ws_record(HarvesterTestUtils.make_ws_dict("EPMC", "TEST"))

    @staticmethod
    def create_live_epmc_ws_record():
        """
        Create EPMC Live harvester webservice
        :return: ID of webservice record or None
        """
        return HarvesterTestUtils.create_ws_record(HarvesterTestUtils.make_ws_dict("EPMC", "LIVE", live_date="2019-01-01"))


    @staticmethod
    def create_default_ws_recs():
        # Create webservice records
        today = datetime.today()
        # PubMed
        # Give a plausible end date to PubMed so it will run next schedule.
        until_date = today - relativedelta(days=current_app.config["DAYS_TO_START_FROM_PUBMED"])
        current_app.config["WEBSERVICES_DATA_PUBMED"]['end_date'] = until_date.strftime("%Y-%m-%d")
        HarvesterTestUtils.create_ws_record(current_app.config["WEBSERVICES_DATA_PUBMED"])

        # EPMC
        # Give a plausible end date to EPMC so it will run next schedule.
        until_date = today - relativedelta(days=current_app.config["DAYS_TO_START_FROM_EPMC"])
        current_app.config["WEBSERVICES_DATA_EPMC"]['end_date'] = until_date.strftime("%Y-%m-%d")
        HarvesterTestUtils.create_ws_record(current_app.config["WEBSERVICES_DATA_EPMC"])
