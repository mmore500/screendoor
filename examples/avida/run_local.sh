#!/usr/bin/env bash
# Skeletonize a few Avida organisms with every policy, as real dispatches
# run by the busy-loop daemon with the subprocess orchestrator. With
# KILL_AFTER_S set, the daemon is SIGKILLed after that many seconds and
# restarted, to show that dispatches resume from their records.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
DISPATCHDIR="${1:-$HERE/work}"
ORGANISMS="${ORGANISMS:-default_heads_50 nand_50}"
POLICIES="${POLICIES:-ddmin minesweeper hybrid}"
mkdir -p "$DISPATCHDIR"
cp -n "$HERE/dispatch_hooks.json" "$DISPATCHDIR/"
for org in $ORGANISMS; do
  for pol in $POLICIES; do
    python3 "$HERE/make_dispatch.py" "$org" --policy "$pol" --search-seed 42 \
      | python3 -m screendoor.daemon.submit_dispatch - --dispatchdir "$DISPATCHDIR"
  done
done
if [ -n "${KILL_AFTER_S:-}" ]; then
  python3 -m screendoor.daemon.run_busyloop --dispatchdir "$DISPATCHDIR" &
  pid=$!
  sleep "$KILL_AFTER_S"
  echo "=== SIGKILL daemon $pid after ${KILL_AFTER_S}s ==="
  kill -9 "$pid" || true
  wait "$pid" || true
  python3 -m screendoor.daemon.print_status --dispatchdir "$DISPATCHDIR"
  echo "=== restarting daemon ==="
fi
python3 -m screendoor.daemon.run_busyloop --dispatchdir "$DISPATCHDIR"
python3 -m screendoor.daemon.print_status --dispatchdir "$DISPATCHDIR"
