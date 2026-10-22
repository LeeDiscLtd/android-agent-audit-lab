#!/bin/bash
set -euo pipefail
source /Users/lee/experiment/scripts/env.sh
ROOT=/Users/lee/experiment
if adb devices | grep -q '^emulator-5554'; then
  adb -s emulator-5554 emu avd name | grep -q '^AuditApi33' || { echo 'Port 5554 belongs to another emulator'; exit 1; }
else
  nohup emulator -avd AuditApi33 -port 5554 -no-window -no-audio -no-boot-anim -no-snapshot -gpu swiftshader_indirect -memory 2048 -cores 2 > "$ROOT/results/emulator.log" 2>&1 &
fi
for attempt in {1..90}; do
  if [[ "$(adb -s emulator-5554 shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" == 1 ]]; then break; fi
  sleep 2
done
[[ "$(adb -s emulator-5554 shell getprop sys.boot_completed | tr -d '\r')" == 1 ]]
# This local fixture does not depend on public captive portal endpoints.
adb -s emulator-5554 shell settings put global captive_portal_mode 0
adb -s emulator-5554 shell svc data disable
adb -s emulator-5554 shell svc data enable
adb -s emulator-5554 shell settings put global window_animation_scale 0
adb -s emulator-5554 shell settings put global transition_animation_scale 0
adb -s emulator-5554 shell settings put global animator_duration_scale 0
if ! curl -fsS http://127.0.0.1:8765/health 2>/dev/null | grep -qx audit-target-download-server-v1; then
  if lsof -n -iTCP:8765 -sTCP:LISTEN >/dev/null; then echo 'Port 8765 is occupied by another server'; exit 1; fi
  nohup "$ROOT/tools/python/bin/python" "$ROOT/scripts/download_server.py" > "$ROOT/results/download-server.log" 2>&1 &
  echo $! > "$ROOT/results/download-server.pid"
fi
adb -s emulator-5554 reverse tcp:8765 tcp:8765
adb -s emulator-5554 install -r "$ROOT/artifacts/audit-target-debug.apk"
adb -s emulator-5554 shell am start -S -n org.example.audittarget/.MainActivity --ez evaluation false --ez injection false
