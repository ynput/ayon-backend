#!/usr/bin/env bash

# Environment variables

SERVER_LOG_LEVEL=${AYON_SERVER_LOG_LEVEL:-warning}
SERVER_WORKERS=${AYON_SERVER_WORKERS:-1}
SERVER_MAX_REQUESTS=${AYON_SERVER_MAX_REQUESTS:-0}
SERVER_MAX_REQUESTS_JITTER=${AYON_SERVER_MAX_REQUESTS_JITTER:-0}
SERVER_TIMEOUT=${AYON_SERVER_TIMEOUT:-120}
SERVER_TYPE=${AYON_SERVER_TYPE:-gunicorn}

[ -z "$AYON_RUN_SETUP" ] && AYON_RUN_SETUP=true
[ -z "$AYON_RUN_SERVER" ] && AYON_RUN_SERVER=true
[ -z "$AYON_RUN_MAINTENANCE" ] && AYON_RUN_MAINTENANCE=true

echo ""
echo "AYON_RUN_SETUP: $AYON_RUN_SETUP"
echo "AYON_RUN_SERVER: $AYON_RUN_SERVER"
echo "AYON_RUN_MAINTENANCE: $AYON_RUN_MAINTENANCE"
echo "SERVER_LOG_LEVEL": $SERVER_LOG_LEVEL
echo "SERVER_WORKERS: $SERVER_WORKERS"
echo ""

# Setup

if [ $AYON_RUN_SETUP = 0 ] || [ $AYON_RUN_SETUP = "false" ]; then
  echo "start.sh: Skipping setup"
else
  echo "start.sh: Starting setup"
  python -m setup --ensure-installed

  if [ $? -ne 0 ]; then
    echo ""
    echo "Error occurred during setup. Please check the logs for more information."
    echo "AYON server cannot start. Terminating..."
    echo ""
    exit 1
  fi
fi

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

if [ $AYON_RUN_SERVER = 0 ] || [ $AYON_RUN_SERVER = "false" ]; then
    # server is disabled. maybe the user wants to run just the
    # maintenance?

    if [ $AYON_RUN_MAINTENANCE = 0 ] || [ $AYON_RUN_MAINTENANCE = "false" ]; then
        echo "start.sh: Both server and maintenance are disabled. Exiting..."
    else
        echo "start.sh: Starting maintenance worker"
        exec python -m maintenance
    fi

else
    if [ $SERVER_TYPE = "gunicorn" ]; then
        echo "start.sh: Starting gunicorn server"
        exec gunicorn \
            -k uvicorn.workers.UvicornWorker \
            --log-level ${SERVER_LOG_LEVEL} \
            --workers ${SERVER_WORKERS} \
            --timeout ${SERVER_TIMEOUT} \
            --max-requests ${SERVER_MAX_REQUESTS} \
            --max-requests-jitter ${SERVER_MAX_REQUESTS_JITTER} \
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
fi
