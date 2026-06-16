"""
Library containing BASH shell scripts which are executed by python modules
"""
from os import path
from flask import current_app

shell_script_dir = None     # Gets initialised the first time that function full_script_path is called

def full_script_path(script_filename):
    """
    Return the full path (including the script filename)
    :param script_filename: String - Name of script file
    :return: String - Full path of script file
    """
    global  shell_script_dir
    # Initialise shell_script_dir variable
    if shell_script_dir is None:
        shell_script_dir = current_app.config.get('SHELL_SCRIPT_DIR')
        if shell_script_dir.startswith('~'):
            shell_script_dir = path.expanduser(shell_script_dir)

    return path.join(shell_script_dir, script_filename)
