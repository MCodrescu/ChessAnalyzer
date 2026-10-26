"""Single-process web deployment; engine admission is process-local."""

import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8080')}"
workers = 1
worker_class = "gthread"
threads = 4
timeout = 180
graceful_timeout = 180
worker_tmp_dir = "/dev/shm"
accesslog = "-"
errorlog = "-"
forwarded_allow_ips = "*"
secure_scheme_headers = {"X-FORWARDED-PROTO": "https"}
