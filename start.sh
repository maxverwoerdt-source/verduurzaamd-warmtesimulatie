#!/bin/sh
set -eu
: "${APP_SECRET_PATH:?APP_SECRET_PATH must be set to a random path token of at least 20 characters}"
# Do not keep a separate LibreOffice daemon alive: Render's 512 MB memory
# limit caused the persistent UNO process to be killed. Calculations start a
# short-lived, isolated LibreOffice process and clean it up after each request.
exec gunicorn --bind 0.0.0.0:${PORT:-10000} --workers 1 --threads 2 --timeout 180 app:app
