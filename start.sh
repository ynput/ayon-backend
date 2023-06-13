#!/usr/bin/env bash

echo "Starting setup"
python -m setup --ensure-installed
echo "Starting server"
gunicorn -k uvicorn.workers.UvicornWorker --log-level warning -b :5000 ayon_server.api:app
