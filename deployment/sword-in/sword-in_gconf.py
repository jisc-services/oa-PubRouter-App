bind = '127.0.0.1:5990'
# workers = 4   ## Can increase to 4 if many publishers use SWORD-IN
workers = 3
worker_connections = 1000
timeout = 1000
keepalive = 2

# see https://github.com/benoitc/gunicorn/blob/master/examples/example_config.py for more config
