#!/bin/bash
set -euo pipefail
source /Users/lee/experiment/scripts/env.sh
if adb -s emulator-5554 emu avd name 2>/dev/null | grep -q '^AuditApi33'; then
  adb -s emulator-5554 emu kill
  for attempt in {1..20}; do
    if ! adb devices | grep -q "^emulator-5554"; then break; fi
    sleep .5
  done
fi
pid_file=/Users/lee/experiment/results/download-server.pid
if [[ -f "$pid_file" ]]; then
  server_pid=$(cat "$pid_file")
  if [[ "$server_pid" =~ ^[0-9]+$ ]] && ps -p "$server_pid" -o args= | grep -q '/Users/lee/experiment/scripts/download_server.py'; then kill "$server_pid"; fi
  rm "$pid_file"
fi
