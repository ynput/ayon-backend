#!/usr/bin/env bash

SERVER_TYPE=${AYON_SERVER_TYPE:-gunicorn}

function get_server_pid () {
  if [ $SERVER_TYPE = "gunicorn" ]; then
    pid=$(ps aux | grep 'gunicorn' | awk '{print $2}')
  elif [ $SERVER_TYPE = "granian" ]; then
    pid=$(ps aux | grep 'granian' | awk '{print $2}')
  fi
  echo $pid
}

echo ""
echo "Reloading the server..."
echo ""
kill -HUP $(get_server_pid) 2> /dev/null
exit 0
