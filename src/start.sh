#!/usr/bin/env bash

set -uxo pipefail

LOG1=/app/tabbyAPI.log
LOG2=/app/handler.log

# Start main.py
(
  cd /app
  python3.11 main.py >> $LOG1 2>&1
) &

# Start handler.py
(
  cd /app
  python3.11 -u handler.py >> $LOG2 2>&1
) &

set +x

# Allow processes to start and then tail logs
sleep 1
tail -f $LOG1 $LOG2