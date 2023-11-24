#!/usr/bin/env bash

# Logging

AYON_LOG_FILE=${AYON_LOG_FILE:-/dev/null}
AYON_LOG_DIR=$(dirname "$AYON_LOG_FILE")
GUNICORN_LOG_LEVEL=${GUNICORN_LOG_LEVEL:-warning}

if [ "$AYON_LOG_FILE" != "/dev/null" ]; then
    mkdir -p "$AYON_LOG_DIR"
fi

# Setup

echo "start.sh: Starting setup"
python -m setup --ensure-installed

# Reload server on signal

function stop_server () {
  echo ""
  echo "SIGTERM signal received. Shutting down..."
  echo ""
  pid=$(ps aux | grep 'gunicorn' | awk '{print $2}')
  kill -TERM $pid 2> /dev/null
  exit 0
}

trap stop_server SIGTERM SIGINT

# Start server

echo "start.sh: Starting server"
gunicorn \
  -k uvicorn.workers.UvicornWorker \
  --log-level ${GUNICORN_LOG_LEVEL} \
  --timeout 120 \
  -b :5000 \
  ayon_server.api.server:app 2>&1 | tee -a "$AYON_LOG_FILE"
