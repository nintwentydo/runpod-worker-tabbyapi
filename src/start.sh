#!/usr/bin/env bash

set -uxo pipefail

LOG=/app/tabbyAPI.log

(
  cd /app
  python3.11 main.py >> $LOG 2>&1
) &

set +x
sleep 1 && tail -f $LOG