"""
Main script which executes the run cycle.

It will start and remain running until it is shut-down externally, and will execute the deposit.run method
repeatedly.
"""
# from octopus.lib.scheduling import init_and_run_schedule
from octopus.core import initialise, add_config_from_module
from octopus.modules.mysql.dao import DAO
from router.shared.models.schedule import Schedule, JobResult, NoJobsScheduled
from router.shared.after_run_actions import database_reset, after_run_action
from router.shared.models.metrics import MetricsRecord
from router.jper_sword_out.app import app
from router.jper_sword_out.deposit import Deposit


def _database_reset():
    """
    Perform a reset / tidy-up of database.
    """
    database_reset(app.logger)
    return None


def _shutdown():
    """
    Cause application to close process.
    """
    return JobResult(job_flag=JobResult.END_SCHEDULE)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config", help="additional configuration to load (e.g. for testing)")
    args = parser.parse_args()

    if args.config:
        add_config_from_module(app, args.config)

    with app.app_context():
        initialise()

        def _after_run():
            # Action to perform after run
            after_run_action(app.logger,
                             app.config.get("SWORD_ACTION_AFTER_RUN"),
                             "After running SWORD-out",
                             Deposit.classes_for_cursor_close())

        # Function declared here after Deposit is initialised in preceding line.
        def sword_out():
            Deposit.init_cls()

            # Once the job has run, we want the schedule (& therefore, the main program) to terminate.
            job_result = JobResult(after_run_action_fn=_after_run)

            metrics = MetricsRecord(server=app.config.get("SERVER_ID", "Dev"), proc_name="SWORD-out", measure="deposit")
            try:
                Deposit.send_notes_to_sword_acs()
            except Exception as e:
                app.logger.critical(f"SWORD-Out run failed: {repr(e)}")
                job_result.exception = e
            finally:
                job_result.count = Deposit.total_deposits
                metrics.log_and_save(log_msg=". Made {} deposit{}", count=Deposit.total_deposits)
                Deposit.graceful_killer.restore_behaviour()
            return job_result

        # maps process strings to their respective functions
        process_map = {"sword_out": sword_out,
                       "database_reset": _database_reset,
                       "shutdown": _shutdown
                       }
        try:
            schedule = Schedule(app.config.get("SERVER_ID", "Dev"),
                                "Sword-out",
                                app.config.get("SCHEDULER_SPEC", []),
                                app.config.get("SCHEDULER_CONFLICTS", {}),
                                process_map,
                                sleep_secs=app.config.get("SCHEDULER_SLEEP"),
                                logger=app.logger,
                                new_day_reload=False    # Not needed as application is shutdown daily (then automatically restarted)
                                )
            schedule.run_schedule()
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
            DAO.abnormal_exit(e, "SWORD-Out ")
