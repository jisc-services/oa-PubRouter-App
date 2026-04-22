#
#   File to run PyTest on test files that are located in directories defined by 'coverage.ini' config file.
#
import os
import getpass
import sys
from configparser import ConfigParser
import pytest

config_file = 'coverage_tests.ini'
# realpath() will make your script run, even if you symlink it :)
# Get dirname and add to sys.path
cmd_folder = os.path.realpath(os.path.dirname(__file__))
if cmd_folder not in sys.path:
    sys.path.insert(0, cmd_folder)

print('**** COVERAGE TESTS ****')
print('\n*** Running:', __file__, ' As user:', getpass.getuser(), ' Using config file:', config_file)
print('\n*** Environment variables:', os.environ)


# Read config from  config file
proj_paths_file_full = os.path.join(cmd_folder, config_file)
print('\n*** Getting locations of tests from file:', proj_paths_file_full)
config = ConfigParser()
config.read(proj_paths_file_full)
paths = []
separator_char = os.sep
for label, path in config.items("PATHS"):
    if separator_char != "/":
        path = path.replace("/", separator_char)
    # Append directory separator if not already present
    if not path.endswith(separator_char):
        path += separator_char
    # Check if the folder in project_paths exists
    cmd_subfolder = os.path.join(cmd_folder, path)
    if os.path.exists(cmd_subfolder):
        paths.append(cmd_subfolder)
        if cmd_subfolder not in sys.path:
            sys.path.insert(0, cmd_subfolder)
    else:
        print(f"** WARNING: directory '{cmd_subfolder}' NOT FOUND")
print('\n*** Paths to tests loaded from config: ', paths)

exit_code = 0
for path in paths:
    print('\n*** Running PYTEST for:', path)
    code = pytest.main(["-x", path])
    # 5 is for folders where tests aren't found, but not failures
    if code not in (0, 5):
        exit_code = code

sys.exit(exit_code)
