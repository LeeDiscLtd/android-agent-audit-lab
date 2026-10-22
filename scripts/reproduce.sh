#!/bin/bash
set -euo pipefail
source /Users/lee/experiment/scripts/env.sh
experiment_root=/Users/lee/experiment
archive="$experiment_root/results/history/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$archive"
for item in acceptance edgecases acceptance.log edgecases.log build-final.log; do
  if [[ -e "$experiment_root/results/$item" ]]; then mv "$experiment_root/results/$item" "$archive/"; fi
done
bash "$experiment_root/scripts/build.sh" > "$experiment_root/results/build-final.log" 2>&1
bash "$experiment_root/scripts/start.sh" > "$experiment_root/results/start.log" 2>&1
"$experiment_root/tools/python/bin/python" "$experiment_root/scripts/verify.py" 2>&1 | tee "$experiment_root/results/acceptance.log"
"$experiment_root/tools/python/bin/python" "$experiment_root/scripts/verify_edges.py" 2>&1 | tee "$experiment_root/results/edgecases.log"
