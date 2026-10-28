#!/usr/bin/env bash
# Runs the PLUTO embeddings pipeline and its checks in order, timing each step.
# Works on macOS (Apple silicon) and on Windows through WSL2.
#
#   bash run_pipeline.sh setup        create the Python env and install requirements (once)
#   bash run_pipeline.sh              every step and check, 01 through 09
#   bash run_pipeline.sh from 07      start at a step (01..09)
#   bash run_pipeline.sh only 04      one step and its check
#   bash run_pipeline.sh web          install web deps and start the dev server (Ctrl+C to stop)
#
# Stops at the first failing step or check. Output also goes to data/processed/run_log.txt.
set -euo pipefail
cd "$(dirname "$0")"
VENV="${VENV:-$HOME/.venvs/pluto-embeddings}"
PY="$VENV/bin/python"

setup() {
  python3 -m venv "$VENV"
  "$PY" -m pip install -U pip wheel
  if command -v nvidia-smi >/dev/null 2>&1; then
    # RTX 50-series (Blackwell) needs the CUDA 12.8 wheels.
    "$PY" -m pip install torch --index-url https://download.pytorch.org/whl/cu128
  fi
  "$PY" -m pip install -r requirements.txt
  "$PY" - <<'EOF'
import torch, pyogrio, shapely, umap
dev = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
print(f"torch {torch.__version__} device {dev}; pyogrio {pyogrio.__version__}; shapely {shapely.__version__}")
if dev == "cuda":
    print(torch.cuda.get_device_name(0))
EOF
}

web() {
  cd web
  npm install
  npm run dev
}

case "${1:-all}" in
  setup) setup; exit 0 ;;
  web) web; exit 0 ;;
esac

[ -x "$PY" ] || { echo "No env at $VENV. Run: bash run_pipeline.sh setup"; exit 1; }
mkdir -p data/processed
LOG=data/processed/run_log.txt
echo "=== $(date '+%Y-%m-%d %H:%M') $(uname -srm) args: $*" >> "$LOG"

# step -> "script [check ...]"
STEPS=(
  "01|01_lots.py|checks/check_join.py checks/check_frontage_queens.py"
  "02|02_frontage.py|"
  "03|03_footprints.py|checks/check_footprints.py"
  "04|04_trees.py|checks/check_trees.py"
  "05|05_acs.py|checks/check_acs.py"
  "06|06_features.py|"
  "07|07_train.py|checks/check_training.py"
  "08|08_layout.py|"
  "09|09_export.py|checks/check_export.py"
)
mode="${1:-all}"; at="${2:-01}"
run() {
  local t0=$SECONDS
  echo ">>> $1" | tee -a "$LOG"
  (cd data/scripts && "$PY" -u $1) 2>&1 | tee -a "$LOG"
  echo "<<< $1 ($((SECONDS - t0)) s)" | tee -a "$LOG"
}
for s in "${STEPS[@]}"; do
  IFS='|' read -r n script checks <<< "$s"
  if [ "$mode" = from ] && [[ "$n" < "$at" ]]; then continue; fi
  if [ "$mode" = only ] && [ "$n" != "$at" ]; then continue; fi
  run "$script"
  for c in $checks; do run "$c"; done
done
echo "Done. Timings: data/processed/timings.json  Checks: data/processed/checks.json" | tee -a "$LOG"
