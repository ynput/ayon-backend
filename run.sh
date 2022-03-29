#!/bin/bash
#python ./wait-for-db.py
python -m setup --ensure-installed
uvicorn "$@" openpype.api:app 
