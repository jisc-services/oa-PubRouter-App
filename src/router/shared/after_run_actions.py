"""
Functions primarily developed to address memory leak issue.

Author: Jisc
"""
from time import sleep
from sys import exit
from octopus.modules.mysql.dao import DAO


def database_reset(logger, info_msg="Database reset"):
    """
    Perform a reset / tidy-up of database.

    :param logger: Logging object
    :param info_msg: Optional msg to log
    """
    # Close all MySQL db connections
    errors = DAO.close_all_connections()
    logger.info(f"{info_msg} - Closing all database connections.")
    if errors:
        logger.info("In database_reset - Closing database connections raised these errors: " + errors)


def shutdown(logger, info_msg="Scheduled exit of application"):
    """
    Terminate the application after closing all database connections.

    Example usage: Used in conjunction with supervisord to effect an automatic restart of the scheduler process (to deal
    with unresolved memory leak).
    """
    database_reset(logger, info_msg)
    sleep(1)    # Sleep 1 second
    logger.info(f"{info_msg} - Shutdown")
    exit()


def close_cursors_for_classes(logger, classes_to_close, info_msg="Close cursors for classes"):
    """
    Close cursors for list of classes.

    :param logger: Logging object
    :param classes_to_close: List of classes for which cursors are to be closed
    :param info_msg: Optional msg to log
    """
    # Close all MySQL cursors for particular classes
    class_names = ", ".join([_cls.__name__ for _cls in classes_to_close])
    logger.info(f"{info_msg} - Closing cursors for {class_names} .")
    errors = []
    for _cls in classes_to_close:
        error_str, _ = _cls.close_cursors_for_class()
        if error_str:
            errors.append(error_str)
    if errors:
        logger.info("In close_cursors_for_classes - Got these errors: " + ", ".join(errors))


def close_all_cursors(logger, info_msg="Cursor close"):
    """
    Close all cursors.

    :param logger: Logging object
    :param info_msg: Optional msg to log
    """
    logger.info(f"{info_msg} - Closing all cursors.")
    error = DAO.close_all_cursors()
    if error:
        logger.info("In close_all_cursors - Last error: " + error)


def after_run_action(logger, action_after_run, info_msg="", class_list=None, log_db_diagnostics=True):
    """
    Action to perform after a run - attempt to mitigate memory leak problems.
    """
    # print(f"\n-- DB DIAGNOSTICS BEFORE After run action '{action_after_run}':", DAO.diagnostics_str())
    if action_after_run:
        if action_after_run == "exit":
            shutdown(logger, info_msg)
        elif action_after_run == "close_conn":
            database_reset(logger, info_msg)
        elif action_after_run == "close_curs":
            close_all_cursors(logger, info_msg)
        elif action_after_run == "close_class_curs" and class_list:
            close_cursors_for_classes(logger, class_list, info_msg)

        if log_db_diagnostics:
            logger.info(f"After run action '{action_after_run}' - db DIAGNOSTICS:" + DAO.diagnostics_str())

    # print(f"\n-- DB DIAGNOSTICS AFTER After run action '{action_after_run}':", DAO.diagnostics_str(), "\n")

