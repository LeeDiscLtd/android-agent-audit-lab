#!/bin/bash
set -euo pipefail
source /Users/lee/experiment/scripts/env.sh
cd /Users/lee/experiment/android-target
gradle --no-daemon --max-workers=4 :app:assembleDebug :app:lintDebug
mkdir -p /Users/lee/experiment/artifacts
cp app/build/outputs/apk/debug/app-debug.apk /Users/lee/experiment/artifacts/audit-target-debug.apk
cd /Users/lee/experiment/artifacts
shasum -a 256 audit-target-debug.apk | tee SHA256SUMS
