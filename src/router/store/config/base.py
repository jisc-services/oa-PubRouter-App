"""
Main configuration file for the STORE application

On deployment, configuration can be overridden by using a local ~/.pubrouter/store.cfg file
"""
import os

SERVER_NAME = 'store'   # This must match the server_name in the Gateway server NGINX virtualhost config for Store
PREFERRED_URL_SCHEME = 'http'

HOST = "localhost"
PORT = 5999
THREADED = True

LOGFILE = "/var/log/pubrouter/store.log"
LOGSIZE = 50000000

LOCAL_CONFIG = os.path.expanduser("~/.pubrouter/store.cfg")
