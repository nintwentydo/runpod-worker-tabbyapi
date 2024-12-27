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
  python3.11 -u handler.py --rp_log_level ERROR
) &

set +x

# Allow processes to start
sleep 1
wait