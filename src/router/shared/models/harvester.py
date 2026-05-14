from flask import current_app
from octopus.lib.exceptions import HarvestError
from router.shared.mysql_dao import HarvWebServiceRecordDAO, HarvErrorRecordDAO, HarvHistoryRecordDAO
from router.jper.views.utility_funcs import calc_num_of_pages
PAGE_SIZE = 25


def harvester_index_name(engine_name, harvester_id):
    """
    Construct name of a harvester's temporary index by combining first 3 characters of engine name with harvester
    record Id.

    :param engine_name: Harvester engine name
    :param harvester_id: Harvester ID
    :return: index name
    """
    return "{}_{}".format(engine_name.lower()[:3], harvester_id)


class HarvErrorsModel(HarvErrorRecordDAO):

    @classmethod
    def get_error_list(cls, page_num, page_size, for_run_id=None):
        """
        Gets List of errors (in descending date order) for a specified page (if set)
        :param page_num: Page number
        :param page_size: Number of records per page
        :param for_run_id: None or Integer - ID of run number for which to retrieve errors
        :return: tuple - (list of error tuples,  total number of pages)
        """
        if for_run_id is None:
            pull_name = "bspk_all"
            cnt_pull_name = "all"
            params = []
        else:
            pull_name = "bspk_all_4hist"
            cnt_pull_name = "all_4hist"
            params = [for_run_id]
        total_recs = cls.count(*params, pull_name=cnt_pull_name)
        # Could use scroller, but max 25 recs retrieved, so not justified at this time
        rec_tuples = cls.bespoke_pull(*params, pull_name=pull_name, limit_offset=[page_size, page_num * page_size])
        return rec_tuples, calc_num_of_pages(page_size, total_recs)

    @classmethod
    def delete_errors_for_ws(cls, ws_id):
        return cls.delete_by_query(ws_id, del_name="for_ws_id")


class HarvHistoryModel(HarvHistoryRecordDAO):

    @classmethod
    def get_hist_rec(cls, id, raise_on_error=False):
        """
        Gets List of history entries (in descending date order) for a specified page (if set)
        :param id: Run id
        :param raise_on_error: Boolean - whether to raise an exception or not
        :return: tuple - (list of error tuples,  total number of pages)
        """
        recs = cls.bespoke_pull(id, pull_name="pk")
        rec_count = len(recs)
        if rec_count != 1:
            if raise_on_error:
                raise Exception(f"Problem retrieving harvester history record with Id: {id} - {rec_count} records found")
            else:
                return None

        id, created, name, url, start_date, end_date, num_received, num_sent, num_errors, ws_id = recs[0]
        return {"id": id,
                "created": created,
                "name": name,
                "url": url,
                "start_date": start_date,
                "end_date": end_date,
                "num_received": num_received,
                "num_sent":num_sent,
                "num_errors": num_errors,
                "ws_id": ws_id
                }

    @classmethod
    def get_history(cls, page_num, page_size):
        """
        Gets List of history entries (in descending date order) for a specified page (if set)
        :param page_num: Page number
        :param page_size: Number of records per page
        :return: tuple - (list of error tuples,  total number of pages)
        """
        total_recs = cls.count(pull_name="all")
        # Scroller NOT needed because relatively small records retrieved & only 1 page (e.g. 25 recs) at a time
        rec_tuples = cls.bespoke_pull(pull_name="bspk_all", limit_offset=[page_size, page_num * page_size])
        return rec_tuples, calc_num_of_pages(page_size, total_recs)

    @classmethod
    def delete_history_for_ws(cls, ws_id):
        return cls.delete_by_query(ws_id, del_name="for_ws_id")


class HarvesterWebserviceModel(HarvWebServiceRecordDAO):
    """
    Queries for retrieving harvester webservice data from database
    """
    @classmethod
    def get_webservices_dicts(cls, status="all"):
        """
        Gets list of all harvester webservices as dicts
        :param: status - String: one of "all"|"active"
        :return: list of webservices record dicts
        """
        return cls.pull_all(pull_name=status, wrap=False)


    @classmethod
    def get_webservice(cls, webservice_id, for_update=False):
        """
        Get single harvester webservice object with all data (accessed as `obj.data`)

        :param webservice_id: ID of webservice record to retrieve
        :param for_update: Boolean - True: start transaction; False: no transaction
        :return: webservice object or raise Exception
        """
        if not webservice_id.isnumeric():
            raise ValueError("A numeric harvester webservice ID must be provided.")
        try:
            return cls.pull(webservice_id, for_update=for_update, raise_if_none=True)
        except Exception as e:
            raise ValueError(f"No harvester webservice record found for id {webservice_id}.")

    @classmethod
    def get_harvester_dicts(cls, pseudo_pub=False, reqd_fields=None):
        """
        Returns list of harvester webservice dicts that are to be displayed as either publishers or harvesters.
        :param pseudo_pub: Boolean: True - return "pseudo-publishers", False - return "true havesters"
        :param reqd_fields: List of webservice fields (dict keys) to retrieve (if None then all are returned)
        :return: list of dicts holding required Harvester data
        """
        rec_dicts = cls.pull_all(1 if pseudo_pub else 0, pull_name="pub_or_not", wrap=False)
        # If reqd_fields list is provided, then return list of dicts containing only those fields.
        return [{field: rec[field] for field in reqd_fields} for rec in rec_dicts] if reqd_fields else rec_dicts

    @classmethod
    def get_test_harvester_ids(cls):
        """
        Returns list of harvester webservice ids for those harvesters that are NOT Live.

        :return: list of ids of Test harvesters
        """
        return [rec[0] for rec in cls.bespoke_pull(pull_name="bspk_test_harv_ids")]

    @classmethod
    def get_auto_enable_harvester_ids(cls, auto_enabled=False):
        """
        Returns list of harvester webservice ids for those harvesters that are set to either Auto-enable or 
        NOT auto-enable.
        :param auto_enabled: Boolean - True: return harvester ids with auto_enable ON;
                                False: return harvester ids with auto_enable OFF
        :return: list of harvester ids
        """
        return [rec[0] for rec in cls.bespoke_pull(1 if auto_enabled else 0, pull_name="bspk_auto_enable_harv_ids")]

    @classmethod
    def toggle_status(cls, webservice_id):
        """
        Activate/Deactivate the webservice
        :param webservice_id: the id of the service to re/deactivate
        """
        # retrieve webservice record
        webservice = cls.get_webservice(webservice_id, for_update=True)
        # switch the active status (True -> False, False -> True)
        webservice.data["active"] = not webservice.data.get("active", False)
        webservice.update()
        return webservice.data["active"]

    @classmethod
    def delete_webservice_rec_and_index(cls, webservice_id):
        """
        Delete a harvester temporary index and the webservice record
        :param webservice_id: ID (unique key) of record to delete
        :return: details of webservice just deleted.
        """
        webservice = cls.get_webservice(webservice_id, for_update=True)
        # Delete the webservice record
        webservice.delete()

        # Delete all associated Errors and History records
        num_errors_deleted = HarvErrorsModel.delete_errors_for_ws(webservice.id)
        num_hist_deleted = HarvHistoryModel.delete_history_for_ws(webservice.id)

        return webservice.data


def create_harvester_index(es_db, engine_name, harv_id, ix_name=None):
    """
    Create ElasticSearch index used by harvester.

    :param es_db: Elasticsearch connector
    :param engine_name: engine name
    :param harv_id: harvester id
    :param ix_name: Name of harvester index to create

    :return: Created index name
    """
    if not ix_name:
        ix_name = harvester_index_name(engine_name, harv_id)
    try:
        # Create index using index name and appropriate elasticsearch mapping structure
        es_db.exec_create_index(ix_name, current_app.config["HARVESTER_MAPPINGS"].get(engine_name.lower()))
    except Exception as err:
        raise HarvestError(f"Error creating index '{ix_name}'", str(err)) from err
    return ix_name


def create_harvester_indexes(es_db):
    """
    Create ElasticSearch indexes used by each harvester.
    :param es_db: Elasticsearch connector
    :return: Tuple: List of data-dicts for each harvester, List of index-names created
    """
    webservice_dicts = HarvesterWebserviceModel.get_webservices_dicts()
    ixs = [create_harvester_index(es_db, harv["engine"], harv["id"]) for harv in webservice_dicts]
    return webservice_dicts, ixs


def delete_harvester_index(es_db, engine_name, harv_id, ix_name=None):
    """
    Delete ElasticSearch index used by harvester.

    :param es_db: Elasticsearch connector
    :param engine_name: engine name
    :param harv_id: harvester id
    :param ix_name: Name of harvester index to delete

    :return: Deleted index name
    """
    if not ix_name:
        ix_name = harvester_index_name(engine_name, harv_id)
    try:
        # Delete index
        es_db.exec_delete_index(ix_name)
    except Exception as err:
        raise HarvestError(f"Error deleting index '{ix_name}'", str(err)) from err
    return ix_name


def delete_harvester_indexes(es_db):
    """
    Delete ElasticSearch indexes used by each harvester.
    :param es_db: Elasticsearch connector
    :return: Tuple: List of data-dicts for each harvester, List of index-names deleted
    """
    webservice_dicts = HarvesterWebserviceModel.get_webservices_dicts()
    ixs = []
    failed = []
    last_err = None
    for harv in webservice_dicts:
        index = harvester_index_name(harv["engine"], harv["id"])
        try:
            es_db.exec_delete_index(index)
            ixs.append(index)
        except Exception as err:
            failed.append(index)
            last_err = err
    if failed:
        raise HarvestError(
            f"Error deleting indexes {failed}, other indexes {ixs} were deleted OK. Last error is shown",
            str(last_err))

    return webservice_dicts, ixs


def clear_harvester_indexes(es_db):
    """
    Delete all records in ElasticSearch indexes used by each harvester.
    :param es_db: Elasticsearch connector
    :return:
    """
    webservice_dicts = HarvesterWebserviceModel.get_webservices_dicts()
    failed = []
    last_err = None
    for harv in webservice_dicts:
        index = harvester_index_name(harv["engine"], harv["id"])
        try:
            es_db.execute_delete_query(index, query=current_app.config["MATCH_ALL"])
        except Exception as err:
            failed.append(index)
            last_err = err
    if failed:
        raise HarvestError(f"Error emptying indexes {failed}. Last error is shown", str(last_err))


