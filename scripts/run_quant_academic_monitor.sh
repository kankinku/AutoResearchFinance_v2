#!/usr/bin/env bash
# Read-only, loopback-only, commit-pinned Quant academic dashboard.
set -euo pipefail
ROOT=/shared/moon-workspace/AutoResearchFinance_v2-phase3-5-1-inventory
SOURCE_ROOT=/shared/moon-workspace/AutoResearchFinance_v2-academic-monitor-timing-2251d49
EXPECTED_SHA=2251d4935395872df9234448ebbb20495d1ea9d6
CHECKPOINT_DIR="$ROOT/state/moon-http/research/academic-gpt-checkpoints"
[[ -f "$SOURCE_ROOT/dashboard/academic_run.py" && -d "$CHECKPOINT_DIR" ]] || exit 1
[[ "$(git -C "$SOURCE_ROOT" rev-parse HEAD)" = "$EXPECTED_SHA" ]] || exit 1
[[ -z "$(git -C "$SOURCE_ROOT" status --porcelain)" ]] || exit 1
[[ -x "$ROOT/.venv/bin/python" ]] || exit 1
cd "$SOURCE_ROOT"
export PYTHONPATH="$SOURCE_ROOT${PYTHONPATH:+:$PYTHONPATH}"
exec "$ROOT/.venv/bin/python" -m dashboard.academic_run \
  --checkpoint-dir "$CHECKPOINT_DIR" --host 127.0.0.1 --port 8085
