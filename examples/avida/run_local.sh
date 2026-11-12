#!/usr/bin/env bash
# End-to-end local run: every policy on several Avida organisms, as real
# dispatches ticked by the busy-loop daemon with the subprocess orchestrator.
# With KILL_AFTER_S set, the daemon is SIGKILLed after that many seconds and
# restarted, to show that dispatches resume from their records.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
WORKDIR="${1:-$REPO/work-avida}"
ORGANISMS="${ORGANISMS:-default_heads_50 nand_50 redundant_nand_50 small_effect_vb_50 evolved_9task_67}"
POLICIES="${POLICIES:-ddmin minesweeper hybrid}"
export PYTHONPATH="$REPO${PYTHONPATH:+:$PYTHONPATH}"
mkdir -p "$WORKDIR"
for org in $ORGANISMS; do
  for pol in $POLICIES; do
    python3 "$HERE/make_dispatch.py" "$org" --policy "$pol" --search-seed 42 \
      --max-procs 64 \
      | python3 -m screendoor.daemon.submit_dispatch - --workdir "$WORKDIR"
  done
done
if [ -n "${KILL_AFTER_S:-}" ]; then
  python3 -m screendoor.daemon.run_busyloop --workdir "$WORKDIR" &
  pid=$!
  sleep "$KILL_AFTER_S"
  echo "=== SIGKILL daemon $pid after ${KILL_AFTER_S}s ==="
  kill -9 "$pid" || true
  wait "$pid" || true
  python3 -m screendoor.daemon.print_status --workdir "$WORKDIR" | head -50
  echo "=== restarting daemon ==="
fi
python3 -m screendoor.daemon.run_busyloop --workdir "$WORKDIR"
python3 -m screendoor.daemon.print_status --workdir "$WORKDIR"
