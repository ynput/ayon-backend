#!/usr/bin/env bash

echo "start.sh: Starting setup"
python -m setup --ensure-installed

function stop_server () {
  echo ""
  echo "SIGTERM signal received. Shutting down..."
  echo ""
  pid=$(ps aux | grep 'gunicorn' | awk '{print $2}')
  kill -TERM $pid 2> /dev/null
  exit 0
}

trap stop_server SIGTERM SIGINT


echo "start.sh: Starting server"
exec gunicorn \
  -k uvicorn.workers.UvicornWorker \
  --log-level warning \
  -b :5000 \
  ayon_server.api:app
  