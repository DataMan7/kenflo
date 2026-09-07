"""Gunicorn production config for KENFLO (behind nginx via Unix socket)."""
import multiprocessing
import os

bind = os.environ.get("KENFLO_BIND", "unix:/run/kenflo/kenflo.sock")
workers = int(os.environ.get("KENFLO_WORKERS", max(2, multiprocessing.cpu_count() * 2 + 1)))
worker_class = "sync"
timeout = 60
graceful_timeout = 30
keepalive = 5
accesslog = os.environ.get("KENFLO_ACCESS_LOG", "-")
errorlog = os.environ.get("KENFLO_ERROR_LOG", "-")
# Bind ownership for nginx
umask = 0o007
