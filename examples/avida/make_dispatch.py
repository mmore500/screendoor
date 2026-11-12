#!/usr/bin/env python3
"""Print a screendoor dispatch (JSON) that skeletonizes an Avida organism.

  python3 make_dispatch.py nand_50 --policy hybrid \\
    | python3 -m screendoor.daemon.submit_dispatch - --workdir work

Acceptance matches knockout_skeleton.AvidaExactOracle: viable, keeps every
wildtype task, and fitness >= (1 - rel_tol) * wildtype fitness.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OLD = os.path.expanduser("~/2026-11-03")

CMD = """\
set -euo pipefail
python3 "$AVIDA_EXAMPLE_DIR/avida_fitness.py" "$sequence"
"""


def make_dispatch(
    organism: str,
    *,
    policy: str = "hybrid",
    batch_size: int = 8,
    rel_tol: float = 0.02,
    search_seed: int | None = None,
    binary: str | None = None,
    config_dir: str | None = None,
    schedule: str = "* * * * *",
    orchestrator: str = "subprocess",
    max_procs: int = 8,
    trial_batchsize: int = 1,
) -> dict:
    with open(os.path.join(HERE, "organisms.json")) as fh:
        organisms = json.load(fh)
    binary = (
        binary
        or os.environ.get("AVIDA_BINARY")
        or shutil.which("avida")
        or os.path.join(OLD, "build/avida/bin/avida")
    )
    config_dir = (
        config_dir
        or os.environ.get("AVIDA_CONFIG_DIR")
        or os.path.join(OLD, "vendor/avida/avida-core/support/config")
    )
    kwargs = {
        "sequence": organisms.get(organism, organism),
        "nop_symbol": "A",
        "cmd": CMD,
        "batch_size": batch_size,
        "rel_tol": rel_tol,
        "require_atleast": ["tasks"],
        "env": {
            "AVIDA_BINARY": os.path.abspath(binary),
            "AVIDA_CONFIG_DIR": os.path.abspath(config_dir),
            "AVIDA_EXAMPLE_DIR": HERE,
        },
    }
    if search_seed is not None:
        kwargs["search_seed"] = search_seed
    d = {
        "meta_project": "default",
        "meta_experiment": "default",
        "meta_treatment": "default",
        "meta_user": subprocess.check_output(["id", "-un"], text=True).strip(),
        "meta_attempt": subprocess.check_output(["date"], text=True).strip(),
        "assay": f"scd.assaylib.skeletonize.{policy}",
        "assay_kwargs": kwargs,
        "schedule": schedule,
        "trial_batchsize": trial_batchsize,
        "trial_batch_timeout": 600,
    }
    if orchestrator == "subprocess":
        d["how_launch"] = "scd.orchestrate.subprocess.launch()"
        d["how_poke"] = "scd.orchestrate.subprocess.poke()"
        d[
            "how_throttle"
        ] = f"scd.orchestrate.subprocess.throttle(max_procs={max_procs})"
    elif orchestrator == "slurm":
        d["how_launch"] = (
            "scd.orchestrate.slurm.launch(" "sbatch_flags='--mem=1G')"
        )
    return d


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    p.add_argument("organism", help="name in organisms.json, or a sequence")
    p.add_argument(
        "--policy",
        default="hybrid",
        choices=["ddmin", "minesweeper", "hybrid"],
    )
    p.add_argument("--batch-size", type=int, default=8)
    p.add_argument("--rel-tol", type=float, default=0.02)
    p.add_argument("--search-seed", type=int, default=None)
    p.add_argument("--schedule", default="* * * * *")
    p.add_argument(
        "--orchestrator", default="subprocess", choices=["subprocess", "slurm"]
    )
    p.add_argument("--max-procs", type=int, default=8)
    p.add_argument("--trial-batchsize", type=int, default=1)
    a = p.parse_args()
    json.dump(
        make_dispatch(
            a.organism,
            policy=a.policy,
            batch_size=a.batch_size,
            rel_tol=a.rel_tol,
            search_seed=a.search_seed,
            schedule=a.schedule,
            orchestrator=a.orchestrator,
            max_procs=a.max_procs,
            trial_batchsize=a.trial_batchsize,
        ),
        sys.stdout,
        indent=2,
    )
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
