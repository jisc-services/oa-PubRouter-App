'''
Created on 06 Nov 2015

Engine invoker

@author: Mateusz.Kasiuba
'''
from flask import current_app
from router.harvester.engine.QueryEngineEPMC import QueryEngineEPMC
from router.harvester.engine.QueryEnginePubMed import PubMedQueryEngine
from router.harvester.engine.QueryEngineCrossref import QueryEngineCrossref
from router.harvester.engine.QueryEngineElsevier import QueryEngineElsevier


def get_engine_from_map(engine_name):
    _config = current_app.config
    engine_map = {
        _config["EPMC"]: QueryEngineEPMC,
        _config["PUBMED"]: PubMedQueryEngine,
        _config["CROSSREF"]: QueryEngineCrossref,
        _config["ELSEVIER"]: QueryEngineElsevier
    }
    engine = engine_map.get(engine_name)
    if not engine:
        raise ValueError(f"Engine '{engine_name}' does not exist.")
    return engine


def get_harvester_engine(engine_name, es_db, url, harvester_id=None, date_start=None, date_end=None, name_ws='noService'):
    engine = get_engine_from_map(engine_name)
    return engine(es_db, url, harvester_id, date_start, date_end, name_ws)


def engine_url_is_valid(engine_name, url):
    engine = get_engine_from_map(engine_name)
    return engine.is_valid(url)
