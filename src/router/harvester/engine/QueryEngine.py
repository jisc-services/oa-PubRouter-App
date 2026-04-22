"""
Created on 21 Oct 2015

Abstract class of engine
Engine control how to execute url to API-s

@author: Jisc
"""
from abc import abstractmethod, ABCMeta
from flask import current_app

from octopus.lib.data import get_orcid_from_url
from octopus.lib.exceptions import HarvestError
from router.shared.models.harvester import harvester_index_name, create_harvester_index, delete_harvester_index


class QueryEngine(metaclass=ABCMeta):

    TYPE_AUTHOR = "author"

    def __init__(self, es_db, engine_name, harvester_id, name_ws, url):
        """
        Query engine constructor.

        :param es_db: elasticsearch database connector
        :param engine_name : name of webservice engine
        :param harvester_id: string Unique ID of the harvester
        :param name_ws : harvester web service name
        :param url : web service url to invoke
        """
        self.config = current_app.config
        self.es_db = es_db
        self.engine_name = engine_name
        self.harvester_id = harvester_id
        self.engine_index = harvester_index_name(engine_name, harvester_id)
        self.harv_name = name_ws
        self.url = url
        self.rank = self.config["HARVESTER_RANKING"].get(engine_name, 3)
        self.logger = current_app.logger
        self.logger.info(f"Creating harvester {name_ws} with engine {engine_name}. URL: {url}.")

    def create_harvester_ix(self):
        """
        Create harvester's index with appropriate mapping (if it doesn't already exist)
        :return: nothing
        """
        # If harvester's index doesn't already exist, then create it
        if not self.es_db.index_exists(self.engine_index):
            create_harvester_index(self.es_db, self.engine_name, self.harvester_id, ix_name=self.engine_index)


    def delete_harvester_ix(self):
        """
        Delete harvester's index
        :return: nothing
        """
        # If harvester's index exists, then delete it
        if self.es_db.index_exists(self.engine_index):
            delete_harvester_index(self.es_db, self.engine_name, self.harvester_id, ix_name=self.engine_index)


    def insert_into_harvester_index(self, items):
        """
        Bulk insert JSON records into a temporary index with lowercase name of webservice
        :param items: List of JSON docs to insert
        :return: Number of successful inserts, or None if no items
        """
        try:
            return self.es_db.execute_bulk_insert_query(self.engine_index, items)
        except Exception as err:
            self.logger.error(f"Exception while bulk inserting into ES for {self.harv_name}: {str(err)}")
            raise err

    def delete_harvester_index_recs(self, ignore_fault=True):
        """
        Delete all records from temporary index associated with this harvester instance
        :param: ignore_fault - If exception occurs then log it, but don't re-raise it
        :return: elastic search response dict
        """
        try:
            return self.es_db.execute_delete_query(self.engine_index, {"match_all": {}})

        except Exception as err:
            err_msg = f"Error deleting temporary records for {self.harv_name} from {self.engine_index}"
            self.logger.error(err_msg)
            if not ignore_fault:
                raise HarvestError(err_msg, repr(err)) from err

    @classmethod
    def _process_author_id(cls, id_type, value):
        """
        Given an id type and a value, return an identifier dict for IncomingNotification.

        If the type is orcid, will attempt to retrieve ID from orcid URL if needed.

        :param id_type: String -  Id type like 'orcid'
        :param value: Actual id value

        :return: ID dict like this: {"type": id_type, "id": value} or None if either id_type or value is empty
        """
        if id_type and value:
            # Always store lowercase identifier-type
            id_type = id_type.lower()
            # For ORCID id's we only want to store the specific ID extracted from URL (if that was provided)
            if id_type == "orcid":
                value = get_orcid_from_url(value)
            return {"type": id_type, "id": value}

        return None

    @abstractmethod
    def execute(self):
        pass
