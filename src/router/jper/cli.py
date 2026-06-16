"""
File for JPER related cli (command line interface) tools

This file is used to add a JPER shell that includes common imports that can be quickly accessed through command line.
"""
from flask import current_app
from router.shared.models.account import AccOrg
from router.shared.models.note import RoutedNotification, UnroutedNotification


def load_cli():
    """
    Load all flask cli related functions and commands
    """

    @current_app.shell_context_processor
    def shell_context_processor():
        """
        Any key in this dictionary will be loaded as a variable inside a flask shell.

        This means you can easily access these without having to do any imports while inside the flask shell,
        which can be useful if you would like to quickly look at database objects and the like.

        The flask shell can be activated by running the command 'flask shell' on the command line.
        """
        return {
            "routed": RoutedNotification,
            "unrouted": UnroutedNotification,
            "account": AccOrg,
            "app": current_app,
        }
