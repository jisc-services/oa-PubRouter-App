from unittest import TestCase
from datetime import datetime

from octopus.core import initialise
from octopus.modules.es.connector import ESConnection
from router.harvester.app import app


class QueryEngineTest(TestCase):
    @classmethod
    def setUpClass(cls):
        super(QueryEngineTest, cls).setUpClass()
        with app.app_context():
            initialise()
            cls.today = datetime.today()
            cls.date_today = datetime.today().date()
            cls.es_db = ESConnection(app.config["ELASTIC_SEARCH_HOST"])
            cls.logger = app.logger
            cls.config = app.config
        print("**** QueryEngineTest - setUpClass executed ****\n")

    def setUp(self):
        super().setUp()
        print("\n****", self._testMethodName, "****\n")
