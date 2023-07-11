#!/bin/bash

python3 -c 'from test import start_server; start_server()'
uvicorn main:app --host 0.0.0.0 --port 8000
