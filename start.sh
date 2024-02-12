#!/usr/bin/env bash

# Environment variables

SERVER_LOG_LEVEL=${AYON_SERVER_LOG_LEVEL:-warning}
SERVER_WORKERS=${AYON_SERVER_WORKERS:-1}
SERVER_TIMEOUT=${AYON_SERVER_TIMEOUT:-120}
SERVER_TYPE=${AYON_SERVER_TYPE:-gunicorn}

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

if [ $SERVER_TYPE = "gunicorn" ]; then
  echo "start.sh: Starting gunicorn server"

  exec gunicorn \
    -k uvicorn.workers.UvicornWorker \
    --log-level ${SERVER_LOG_LEVEL} \
    --workers ${SERVER_WORKERS} \
    --timeout ${SERVER_TIMEOUT} \
    -b :5000 \
    ayon_server.api.server:app

elif [ $SERVER_TYPE = "granian" ]; then
  echo "start.sh: Starting granian server"

  exec granian \
    --interface asgi \
    --log-level ${SERVER_LOG_LEVEL} \
    --host 0.0.0.0 \
    --port 5000 \
    ayon_server.api.server:app

else
  echo ""
  echo "Error: invalid server type '$SERVER_TYPE'. Expected 'gunicorn' or 'granian'"
  echo ""
  exit 1
fi
