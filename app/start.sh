#!/bin/bash

python3 -c 'from test import start_server; start_server()'
chmod -R 777 db
uvicorn main:app --host 0.0.0.0 --port 8000
echo 'start.sh run'
