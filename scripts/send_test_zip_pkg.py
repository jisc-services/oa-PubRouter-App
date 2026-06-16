"""
This script is used to make a TEST submission to the Router API /notification or /validation endpoint.
"""
import requests
import argparse

parser = argparse.ArgumentParser()

# set up the argument parser with various different argument options
parser.add_argument("-k", "--apikey", help="API Key for publisher account")
parser.add_argument("-f", "--filename", help="Filename of zip file")
parser.add_argument("-p", "--filepath", help="File path to zip file (including filename)")
parser.add_argument("-n", "--notification", action="store_true", help="Send to notification endpoint")
parser.add_argument("-v", "--validation", action="store_true", help="Send to validation endpoint")
parser.add_argument("-env", "--environment",  help="Send to environment, one of: d|t|u (Development|Test|UAT)")

# TODO: Complete this script  (meanwhile - `see set_test_zip_pkg.sh` shellscript).

