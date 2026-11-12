#!/usr/bin/env python3
"""Score one Avida genome with the Test CPU (analyze mode); print a result.

Usage: avida_fitness.py SEQUENCE   (or set $sequence)

Knocked-out sites are already replaced by nop-X ("A"); this script appends
``INST nop-X`` to instset-heads.cfg so that symbol exists. Prints

  !!!screendoor:payload {"score": fitness, "viable": ..., "tasks": [...], ...}

Environment: AVIDA_BINARY (path to avida), AVIDA_CONFIG_DIR (avida-core/
support/config). Standard library only.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

TASKS = ("not", "nand", "and", "orn", "or", "andn", "nor", "xor", "equ")


def instset_with_nop_x(config_dir: str) -> str:
    with open(os.path.join(config_dir, "instset-heads.cfg")) as fh:
        text = fh.read()
    if any(
        line.split("#", 1)[0].strip() == "INST nop-X"
        for line in text.splitlines()
    ):
        return text
    return text.rstrip() + "\nINST nop-X\n"


def analyze(sequence: str, binary: str, config_dir: str) -> dict:
    with tempfile.TemporaryDirectory(prefix="avida_sd_") as tmp:
        for name in ("avida.cfg", "environment.cfg", "default-heads.org"):
            shutil.copyfile(
                os.path.join(config_dir, name), os.path.join(tmp, name)
            )
        with open(os.path.join(tmp, "instset-heads.cfg"), "w") as fh:
            fh.write(instset_with_nop_x(config_dir))
        with open(os.path.join(tmp, "events.cfg"), "w") as fh:
            fh.write("# no events\n")
        with open(os.path.join(tmp, "analyze.cfg"), "w") as fh:
            fh.write(
                f"LOAD_SEQUENCE {sequence}\nRECALCULATE\n"
                "DETAIL detail.dat sequence viable merit gest_time "
                "fitness "
                + " ".join(f"task.{i}" for i in range(len(TASKS)))
                + "\n"
            )
        subprocess.run(
            [
                binary,
                "-a",
                "-set",
                "ANALYZE_FILE",
                "analyze.cfg",
                "-set",
                "VERBOSITY",
                "0",
            ],
            cwd=tmp,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        with open(os.path.join(tmp, "data", "detail.dat")) as fh:
            rows = [
                ln.split()
                for ln in fh
                if ln.strip() and not ln.startswith("#")
            ]
    if len(rows) != 1 or rows[0][0] != sequence:
        raise RuntimeError(f"unexpected detail.dat rows: {rows!r}")
    p = rows[0]
    return {
        "score": float(p[4]),
        "viable": bool(int(p[1])),
        "merit": float(p[2]),
        "gestation_time": int(p[3]),
        "tasks": [int(x) for x in p[5:]],
    }


def main() -> int:
    seq = sys.argv[1] if len(sys.argv) > 1 else os.environ["sequence"]
    binary = os.environ.get("AVIDA_BINARY") or shutil.which("avida")
    config_dir = os.environ["AVIDA_CONFIG_DIR"]
    result = analyze(seq, binary, config_dir)
    print("!!!screendoor:payload " + json.dumps(result), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
