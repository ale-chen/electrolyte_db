#!/bin/bash

python3 -c 'from test import start_server; start_server()'
chown -R www-data:www-data /app/my_project/app/db
chmod 666 /app/my_project/app/db/experiment_db.sqlite
uvicorn main:app --host 0.0.0.0 --port 8000
echo 'start.sh run'
