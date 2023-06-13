#!/usr/bin/env bash

# This script is used to reload the server without restarting the whole container
# by sending a HUP signal to the gunicorn process.

pid=$(ps aux | grep 'gunicorn' | awk '{print $2}' | head -n 1)
kill -HUP $pid 2> /dev/null
