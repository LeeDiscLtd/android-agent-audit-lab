#!/bin/bash
set -euo pipefail
source /Users/lee/experiment/scripts/env.sh
export EXPERIMENT_DEVICE=emulator-5554
exec /Users/lee/experiment/tools/python/bin/python /Users/lee/experiment/scripts/authorization/run.py
