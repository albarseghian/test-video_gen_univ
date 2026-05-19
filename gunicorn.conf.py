import multiprocessing
import os

# Binding
bind = "0.0.0.0:5000"

# Concurrency
# We use 'gthread' because it's built-in and stable for I/O bound tasks like polling.
# This allows each worker to handle multiple concurrent progress requests.
worker_class = 'gthread'
workers = multiprocessing.cpu_count() * 2 + 1
threads = 4

# Timeout
# Since heavy work is in background threads, the HTTP timeout is less critical,
# but we keep it high to allow for large file uploads.
timeout = 600

# Logging
# Switch from 'debug' to 'info' to avoid filling up disk with polling logs.
loglevel = 'info'
accesslog = '-'  # Log to stdout
errorlog = '-'   # Log to stderr

# Security
# If you are using Nginx to handle SSL, this helps Gunicorn understand the protocol
secure_scheme_headers = {'X-FORWARDED-PROTOCOL': 'ssl', 'X-FORWARDED-PROTO': 'https', 'X-FORWARDED-SSL': 'on'}
forwarded_allow_ips = '*'
