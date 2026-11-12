#!/bin/bash
# Build the single-file screendoor.pyz attached to each release.
# Run its worker as: python3 screendoor.pyz worker --dispatchdir ... --dispatch ...
set -euo pipefail
cd "$(dirname "$0")/.."
version="$(python3 -c 'import screendoor; print(screendoor.__version__)')"
stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT
cp -r screendoor "$stage/"
find "$stage" -name __pycache__ -prune -exec rm -rf {} +
cat > "$stage/__main__.py" <<'PY'
import runpy
import sys

from screendoor.__main__ import COMMANDS as MODULES

# short names: the module's last part, e.g. worker, submit_daemon
COMMANDS = {m.rsplit(".", 1)[-1]: m for m in MODULES}
if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
    sys.exit(f"usage: screendoor.pyz {{{','.join(COMMANDS)}}} ...")
module = COMMANDS[sys.argv.pop(1)]
sys.argv[0] = module
runpy.run_module(module, run_name="__main__", alter_sys=True)
PY
mkdir -p dist
python3 -m zipapp "$stage" -p "/usr/bin/env python3" \
  -o "dist/screendoor-$version.pyz"
echo "dist/screendoor-$version.pyz"
