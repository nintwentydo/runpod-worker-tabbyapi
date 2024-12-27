#!/usr/bin/env bash

set -uxo pipefail

# Start main.py
(
  cd /app
  python3.11 -u main.py
) &

# Start handler.py
(
  cd /app
  python3.11 -u handler.py
) &

set +x

# Allow processes to start
sleep 1
wait