#!/usr/bin/env python3
"""Score one Avida genome on the Test CPU and print a screendoor payload.

    avida_fitness.py SEQUENCE    (or set $sequence)

Avida runs in the devosoft/avida container, as `singularity exec
$AVIDA_IMAGE` (default docker://ghcr.io/devosoft/avida:latest). Knocked-out
sites arrive replaced by nop-X ("A"), which is added to the instruction
set. Prints

    !!!screendoor:payload {"score": fitness, "viable": ..., "tasks": [...]}
"""

import json
import os
import subprocess
import sys
import tempfile

IMAGE = os.environ.get("AVIDA_IMAGE", "docker://ghcr.io/devosoft/avida:latest")
AVIDA = "/avida/cbuild/work/avida"
CONFIG = "/avida/avida-core/support/config"
TASKS = ("not", "nand", "and", "orn", "or", "andn", "nor", "xor", "equ")

# run in the work directory: copy the default configs in, give the
# instruction set nop-X, then analyze
SCRIPT = f"""\
set -e
cp {CONFIG}/avida.cfg {CONFIG}/environment.cfg {CONFIG}/default-heads.org .
cp {CONFIG}/instset-heads.cfg .
grep -q '^INST nop-X' instset-heads.cfg || printf '\\nINST nop-X\\n' >> instset-heads.cfg
exec {AVIDA} -a -set ANALYZE_FILE analyze.cfg -set VERBOSITY 0
"""


def analyze(sequence: str) -> dict:
    """Recalculate `sequence` on the Test CPU and return its fitness,
    viability, merit, gestation time and task counts."""
    detail = "DETAIL detail.dat sequence viable merit gest_time fitness "
    detail += " ".join(f"task.{i}" for i in range(len(TASKS)))
    with tempfile.TemporaryDirectory(prefix="avida-") as work:
        with open(os.path.join(work, "events.cfg"), "w") as fh:
            fh.write("# no events\n")
        with open(os.path.join(work, "analyze.cfg"), "w") as fh:
            fh.write(f"LOAD_SEQUENCE {sequence}\nRECALCULATE\n{detail}\n")
        subprocess.run(
            ["singularity", "--silent", "exec", "--bind", work, "--pwd", work]
            + [IMAGE, "sh", "-c", SCRIPT],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        with open(os.path.join(work, "data", "detail.dat")) as fh:
            rows = [
                line.split()
                for line in fh
                if line.strip() and not line.startswith("#")
            ]
    if len(rows) != 1 or rows[0][0] != sequence:
        raise RuntimeError(f"unexpected detail.dat rows: {rows!r}")
    _, viable, merit, gest_time, fitness, *tasks = rows[0]
    return {
        "score": float(fitness),
        "viable": bool(int(viable)),
        "merit": float(merit),
        "gestation_time": int(gest_time),
        "tasks": [int(x) for x in tasks],
    }


def main() -> int:
    sequence = sys.argv[1] if len(sys.argv) > 1 else os.environ["sequence"]
    print("!!!screendoor:payload " + json.dumps(analyze(sequence)), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
