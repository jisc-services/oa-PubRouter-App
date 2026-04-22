"""
Contains the two classes required for both running and killing a working instance of Harvester
"""
from datetime import date
from logging import CRITICAL

from dateutil.relativedelta import relativedelta
from time import sleep

from octopus.core import initialise
from octopus.lib.exceptions import Error, InputError, HarvestError, ElasticError
# from octopus.lib.scheduling import init_and_run_schedule
from octopus.modules.logger.logger import ERROR_X
from octopus.modules.es.connector import ESConnection
from octopus.modules.es.scroller import Scroller
from octopus.lib.dates import ymd_to_datetime
from octopus.lib.data import truncate_string
from octopus.lib.killer import ProcessKilled, StandardGracefulKiller
from octopus.modules.mysql.dao import DAO, DAOException
from router.shared.models.schedule import Schedule, JobResult, NoJobsScheduled
from router.shared.models.note import HarvestedNotification
from router.shared.models.metrics import MetricsRecord
from router.shared.models.harvester import HarvesterWebserviceModel, HarvHistoryModel, HarvErrorsModel
from router.harvester.engine.GetEngine import get_harvester_engine
from router.harvester.app import app, app_decorator


class Harvester:
    """
    This class provides several function to retrieve article metadata (and possibly fulltext articles) from
    different publication sources such as Crossref, PubMed etc. which are known as harvester web-service providers.

    The data harvested from the providers is temporarily stored in an Elasticsearch index.

    After filtering to refine the harvested article data it is used to create Unrouted notifications..
    """

    SLEEP_TIME = 120  # Seconds (2 mins)
    TRY_TIMES = 3

    killer = None
    error_msgs = []
    processed_ids = []
    num_db_errors = None
    es_conn = None
    provider = None
    provider_id = None
    hist_id = None

    @classmethod
    def create_error_record(cls, error="", url="", notification=""):
        """
        This function insert a record in h_errors table in database.

        :param error: error message
        :param url: web service url
        :param notification: doc notification json

        :return Id of created error record or empty string
        """
        error_doc = {
            'created': None,
            'ws_id': cls.provider_id,
            'hist_id': cls.hist_id,
            'error': error,
            'url': url,
            'document': notification
        }
        try:
            err_obj = HarvErrorsModel(error_doc)
            rec_dict = err_obj.insert()
            rec_id = rec_dict.get('id')
            app.logger.info(f"Error record Id {rec_id} added to 'h_errors' table")
            cls.num_db_errors += 1
            return rec_id
        except Exception as e:
            app.logger.error(f"Failed to insert error record in 'h_errors' table. {str(e)}")
            return None

    @classmethod
    def create_unrouted_notifications(cls, documents, query_engine):
        """
        This function receives a list of documents which passed the filter and converts them into IncomingNotifications
        and sends them to router.

        :param documents: list retrieved from DB with filter applied
        :param query_engine: engine to process the notifications

        :return: tuple ( number-Harvester-unrouted-notifications-saved, Boolean-success-indicator)
        """
        MAX_ERRS_TO_WRITE = 5
        MAX_DB_ERRORS = 2

        #
        ### Convert harvested records into Harvester Notifications
        #
        api_version = app.config.get("API_VERSION")
        error_rec_ids = []  # List of ids of error records created in harvester error index
        num_conversion_faults = 0
        db_errors = 0
        unrouted_saved = 0
        # Loop through harvested documents to produce a list of notifications in IncomingNotification format.
        for doc in documents:
            if cls.killer.killed:
                break
            rec = doc['_source']
            try:
                note_dict = query_engine.convert_to_notification(rec, service_id=query_engine.harvester_id)
                note_dict["vers"] = api_version
                harv_unrouted_note = HarvestedNotification(note_dict)
                harv_unrouted_note.insert()
                unrouted_saved += 1
                cls.processed_ids.append(doc['_id'])
            except Exception as err:
                is_conversion_error = isinstance(err, InputError)
                err_msg = repr(err)
                app.logger.error(f"Notification {'conversion' if is_conversion_error else 'creation'} error occurred - {err_msg}")
                if isinstance(err, DAOException):
                    err_rec_id = cls.create_error_record(err_msg, query_engine.url)
                    error_rec_ids.append(str(err_rec_id))
                    db_errors += 1
                    # Bail out if number of Database errors exceeds maximum allowed
                    if db_errors >= MAX_DB_ERRORS:
                        app.logger.error(f"Database errors reached permitted maximum ({MAX_DB_ERRORS}) - abandoning...")
                        break
                else:
                    cls.processed_ids.append(doc['_id'])
                    num_conversion_faults += 1
                    # Limit the number of errors logged - to potentially avoid hundreds of entries
                    if num_conversion_faults <= MAX_ERRS_TO_WRITE:
                        err_rec_id = cls.create_error_record(
                            err_msg, query_engine.url, str(rec) if is_conversion_error else str(note_dict))
                        error_rec_ids.append(str(err_rec_id))

        # If any errors occurred
        if num_conversion_faults or db_errors:
            err_str = "{} notification creation error(s) occurred, {} 'h_errors' table with Id(s): {}".format(
                num_conversion_faults + db_errors,
                "see" if num_conversion_faults <= MAX_ERRS_TO_WRITE else f"the first {MAX_ERRS_TO_WRITE} are in",
                ", ".join(error_rec_ids))
            cls.error_msgs.append(err_str)

        # returns: ( Number of Unrouted notifications saved , success indicator )
        return unrouted_saved, db_errors == 0

    @classmethod
    def get_article_metadata_from_provider(cls, query_engine):
        """
        This function executes the harvesting engine's API query (to retrieve records from provider) and
        controls the retries and sleep time.

        :param: query_engine: harvester engine (web-service)

        :return: number of records harvested from web-service provider
        """
        loop_count = 0
        # Loop until harvester instance executes successfully, or maximum number of attempts is reached
        while True:
            try:
                # Retrieve all the articles from the web-service provider and put them into the harvester's ES index
                return query_engine.execute()
            except Error as err:
                loop_count += 1
                app.logger.error(f"Failed to retrieve records from harvester {query_engine.harv_name} - {str(err)}")
                # 500 error occurred and not yet reached limit
                if err.code == 500 and loop_count < cls.TRY_TIMES:
                    # Empty the temporary index that is populated by the execute() function
                    query_engine.delete_harvester_index_recs()
                    sleep_time = loop_count * cls.SLEEP_TIME
                    app.logger.info(f"--- Retrying - sleeping {sleep_time} seconds, num_retry {loop_count}")
                    sleep(sleep_time)
                else:
                    raise err
        # return - from the while loop above

    @classmethod
    def check_frequency(cls, frequency, last_date, until_date):
        """
        Checks whether for given frequency, the until_date is long enough past the last_date to run harvester for
        the current provider.

        :param frequency: one of 'daily', 'weekly' or 'monthly'.
        :param last_date: Date object - Last time this provider ran.
        :param until_date: Date object - End date of current provider settings.

        :return: Date object - until_date if we should run, otherwise None.
        """
        freq_map = {
            "daily": lambda date_: date_,
            "weekly": lambda date_: date_ - relativedelta(days=7),
            "monthly": lambda date_: date_ - relativedelta(months=1)
        }
        until_date = freq_map.get(frequency, lambda date_: None)(until_date)
        if until_date:
            if last_date >= until_date:
                until_date = None
                app.logger.info(f"Last time checked was too recent. Frequency is {frequency}")
        else:
            app.logger.error(f"Bad harvester frequency ({frequency})'; allowed values: 'daily', 'weekly', 'monthly'.")

        return until_date   # Date object


    @classmethod
    def harvest_provider_and_create_unrouted_notes(cls, last_run_date, until_day_before):
        """

        :param last_run_date:   Date obj
        :param until_day_before: Date obj
        :return: Tuple (Int- num_recs_harvested, Int- total_unrouted_notifications, Boolean-All-OK)
        """
        query_engine = None
        try:
            cls.killer.exception_if_killed(True)    # If interrupt occurs, we want to raise ProcessKilled exception
            # We retrieve the correct engine for the web-service provider
            query_engine = get_harvester_engine(cls.provider['engine'],
                                                cls.es_conn,
                                                cls.provider['url'],
                                                cls.provider['id'],
                                                last_run_date,
                                                until_day_before,
                                                cls.provider['name'])
            query_engine.create_harvester_ix()  # Create index (if it doesn't already exist)


            ### Step 1: Harvest (retrieve) records from provider and insert them into Elasticsearch
            num_recs_harvested = cls.get_article_metadata_from_provider(query_engine)
            app.logger.info(f"NumFilesReceived: {num_recs_harvested}")
        except (Exception, ProcessKilled) as err:
            if query_engine:
                # delete the temporary index in case something was inserted before failing
                query_engine.delete_harvester_ix()
            if isinstance(err, ProcessKilled):
                raise err
            else:
                raise HarvestError(f"Problem with harvester {cls.provider['name']}. {str(err)}") from err
        finally:
            cls.killer.exception_if_killed(False)    # DON'T raise ProcessKilled exception if interrupt occurs


        ### Step 2: Select harvested records that contain potential matching data (affiliations, funding, ORCIDs etc.)
        ###         create harvested unrouted notifications
        cls.processed_ids = []  # Stores Ids of harvester index records that we never want to reprocess
        total_unrouted_notifications = 0
        all_ok = True
        if num_recs_harvested:
            try:
                # Apply an Elasticsearch filter (defined by the particular harvester engine) to the documents in the
                # database to retrieve a final set which are to be converted into UNROUTED NOTIFICATIONS.
                scroll = Scroller(cls.es_conn)
                scroll.initialize_scroll(query_engine.engine_index, cls.provider['query'])
                for hits in scroll.iterator():
                    num_sent, success = cls.create_unrouted_notifications(hits, query_engine)
                    total_unrouted_notifications += num_sent
                    if not success or cls.killer.killed:
                        # If we couldn't save some notifications, don't delete the index afterwards
                        # so we can send these notifications another time.
                        all_ok = False
                        break

            except Exception as err:
                # At this point, we've already retrieved all the documents for this webservice.
                # We don't want to jump out as we do want to record how many were successful before the failure
                # add the error data here and continue as if we just failed to send some notifications.
                message = repr(err)
                app.logger.error(f"Error retrieving documents with the chosen filter. {message}")
                cls.create_error_record(message, "", cls.provider['query'])
                cls.error_msgs.append(truncate_string(message, 90))
                # Don't delete the rest of the elasticsearch documents because we can continue with them next time
                all_ok = False

        if all_ok:
            query_engine.delete_harvester_ix()
        else:
            try:
                app.logger.info("Deleting {} processed records from index {} for harvester {}".format(
                        len(cls.processed_ids), query_engine.engine_index, query_engine.harv_name))
                # Delete processed records, so they aren't re-processed next time this harvester engine runs
                cls.es_conn.execute_bulk_delete(query_engine.engine_index, cls.processed_ids)
            except Exception as err:
                app.logger.error(
                    f"Problem bulk deleting processed harvester records, deleting index instead. {repr(err)}")
                # Better to lose some records than reprocess previously processed records (because their deletion failed)
                query_engine.delete_harvester_ix()

        return num_recs_harvested, total_unrouted_notifications, all_ok

    @classmethod
    def harvest_from_provider(cls, last_run_date, until_date):
        """
        This function retrieves all the documents from the web-service provider, filters these documents and
        sends them to the router in the proper json format.

        :param: last_run_date: Date obj - last date the query was executed
        :param: until_date: Date obj - until date
        """
        all_ok = False
        cls.error_msgs = []
        cls.num_db_errors = 0  # Num errors written to database
        num_recs_harvested = 0
        num_notifications = 0
        try:
            until_day_before = until_date - relativedelta(days=1)
            end_date_str = until_day_before.strftime("%Y-%m-%d")
            # Note that pub_year is only used by Crossref and will be ignored for other providers
            provider_url = cls.provider['url'].format(
                start_date=last_run_date.strftime("%Y-%m-%d"),
                end_date=end_date_str,
                pub_year=(until_day_before - relativedelta(years=app.config["CROSSREF_PUB_YEARS"])).strftime('%Y'))

            # initialise history record
            history_obj = HarvHistoryModel({
                'created': None,
                'ws_id': cls.provider_id,
                'url': provider_url,
                'query': cls.provider['query'],
                'start_date': cls.provider['end_date'],
                'end_date': end_date_str,
                'num_received': 0,
                'num_sent': 0,
                'num_errors': 0
            })
            history_obj.insert()
            cls.hist_id = history_obj.id

            if not cls.killer.killed:
                num_recs_harvested, num_notifications, all_ok = cls.harvest_provider_and_create_unrouted_notes(last_run_date, until_day_before)
                # If no exceptions... Update last run date for provider
                cls.provider["end_date"] = until_date.strftime("%Y-%m-%d")
                HarvesterWebserviceModel(cls.provider).update()
        except ProcessKilled:
            pass
        except Exception as err:
            app.logger.error(f"Problem with harvester {cls.provider['name']}. {repr(err)}")
            cls.error_msgs.append(err.message if hasattr(err, 'message') and err.message else str(err))
            cls.create_error_record(str(err), provider_url)
        finally:
            # We save the history record with the number of articles retrieved from the web-service provider,
            # the number of notifications created and the errors we've got during the process.
            summary_errors = "\n— ".join(cls.error_msgs)
            # If any errors occurred
            if summary_errors:
                # raise critical error to ensure email is sent
                app.logger.log(ERROR_X if all_ok else CRITICAL, f"Harvester '{cls.provider['name']}' error summary:\n— {summary_errors}",
                                    extra={"subject": f"Harvester '{cls.provider['name']}' errors"})
            # Update history record with numbers
            history_obj.data["num_received"] = num_recs_harvested
            history_obj.data["num_sent"] = num_notifications
            history_obj.data["num_errors"] = cls.num_db_errors
            history_obj.update()

        return num_recs_harvested

    @classmethod
    @app_decorator
    def harvest_all_providers(cls):
        """
        Harvester executes harvesting engines known as "web-service providers", which are defined in Elasticsearch
        h_webservices index.

        Each call to a harvesting engine has the effect of:
           1. Making API calls to harvesting endpoint(s) specified in the web-service provider record (for example, to
              PubMed endpoint) to retrieve records potentially of interest which are stored in a temporary index
           2. Filtering the results in the temporary index using an elasticsearch query (also stored in the web-service
              provider record) to extract a final set of records for converting into Unrouted Notifications
           3. Creates the Unrouted Notifications
           4. Finally, it saves historic information about the queries applied, filter used, number of records processed
              and any errors.

        :return: Tuple (Number of harvester engine web service providers processed or None, total_recs_harvested)
        """
        try:
            # Retrieve all the active harvesters (web-service providers)
            active_harvesters_dicts = HarvesterWebserviceModel.get_webservices_dicts("active")
        except Exception as err:
            app.logger.error("Could not retrieve harvester webservice records. " + str(err))
            return 0, 0

        num_providers = 0
        total_recs_harvested = 0
        if not active_harvesters_dicts:
            app.logger.info('No active harvester providers found, exit')

        # For each of the active provider we process the information returned
        for harvester_dict in active_harvesters_dicts:
            # if we received a kill signal we need to cease harvesting
            if cls.killer.killed:
                break
            last_run_date = ymd_to_datetime(harvester_dict['end_date']).date()

            # Establish the end-date for this harvest - it depends on the harvest frequency (e.g. daily, weekly etc)
            # and the "wait-window" (the number of days by which a harvest is delayed)
            until_date = cls.check_frequency(harvester_dict['frequency'],
                                             last_run_date,
                                             date.today() - relativedelta(days=int(harvester_dict['wait_window'])))
            if until_date:
                num_providers += 1
                cls.provider = harvester_dict
                cls.provider_id = harvester_dict["id"]
                total_recs_harvested += cls.harvest_from_provider(last_run_date, until_date)
            else:
                app.logger.info(f"Did not run {harvester_dict.get('name')} as last time checked was too recent")

        return num_providers, total_recs_harvested


    @classmethod
    def run(cls):
        """
        Harvester runner. When invoked, it will connect to the ES (ElasticSearch) DB and will start the harvester
        process (main). Once the process has finished the connection will be closed.
        """
        metrics = MetricsRecord(server=app.config.get("SERVER_ID", "Dev"), proc_name="Harvest", measure="rec")
        num_providers = total_recs_harvested = 0
        job_result = JobResult()
        cls.killer = StandardGracefulKiller(app.logger, "Harvester")
        try:
            # Get connection to the ES DB for all the task involved; set long timeout as processing large bulk transactions
            cls.es_conn = ESConnection(app.config["ELASTIC_SEARCH_HOST"], request_timeout=20, logger=app.logger)
            # Main harvester process.
            cls.killer.allow_protected_exit("harvest_all_providers")
            num_providers, total_recs_harvested = cls.harvest_all_providers()
        except ElasticError as err:
            app.logger.critical(f"Harvest failed - couldn't connect to Elasticsearch - {repr(err)}")
        except Exception as e:
            job_result.exception = e
        except ProcessKilled:
            pass
        finally:
            if cls.es_conn:
                # Close the connection to Elasticsearch.
                cls.es_conn.close()
            metrics.log_and_save(log_msg=f". Harvested {{}} record{{}} from {num_providers} providers",
                                 count=total_recs_harvested)
            job_result.count = total_recs_harvested
            job_result.func_return = (num_providers, total_recs_harvested)
            # Terminate the program after running harvester - KILL_SCHEDULE & END_SCHEDULE have same result,
            # but report different reasons for schedule (& therefore the program) ending.
            job_result.job_flag = JobResult.KILL_SCHEDULE if cls.killer.killed else JobResult.END_SCHEDULE
            cls.killer.restore_behaviour()

        return job_result


if __name__ == '__main__':
    """
    Run Harvester schedule
    """
    with app.app_context():
        msg = "Harvester scheduler - running --------------------------------"
        print(msg)
        initialise()
        app.logger.info(msg)

        try:
            # maps process strings to their respective functions
            process_map = {"harvest": Harvester.run}

            # If END_SCHEDULE flag gets set, then end as soon as any primer jobs created by this process have been actioned
            # or 15 minutes have elapsed
            schedule = Schedule(app.config.get("SERVER_ID", "Dev"),
                                "Harvest",
                                app.config.get("SCHEDULER_SPEC", []),
                                app.config.get("SCHEDULER_CONFLICTS", {}),
                                process_map,
                                sleep_secs=app.config.get("SCHEDULER_SLEEP"),
                                logger=app.logger,
                                end_if_no_jobs=False,   # If no jobs found in jobs database (due to purge elsewhere) simply reload schedule
                                defer_end=15,
                                new_day_reload=False    # Not needed as application is shutdown daily (then automatically restarted)
                                )
            end_flag = schedule.run_schedule()
            if end_flag == JobResult.KILL_SCHEDULE:
                app.logger.critical("Harvester terminated early by system interrupt.",
                                    extra={"subject": "Harvester interrupted"})
            schedule.purge_jobs_for_server_prog()
            # Close all MySQL db connections
            DAO.close_all_connections()
        except (ValueError, NoJobsScheduled) as e:
            msg = f"**** TERMINATING with exception: {repr(e)}"
            app.logger.critical(msg, extra={"subject": "Scheduler problem"})
            print("\n", msg)
            exit(1)
        except Exception as e:
            schedule.purge_jobs_for_server_prog()
            DAO.abnormal_exit(e, "Harvester ")

