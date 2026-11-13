#!/usr/bin/env python3
"""Print a screendoor dispatch (JSON) that skeletonizes an Avida organism.

  python3 make_dispatch.py nand_50 --policy hybrid \\
    | python3 -m screendoor.daemon.submit_dispatch - --dispatchdir work

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


def sequence_of(organism: str, organisms: dict) -> str:
    """The genome named ``organism``, or ``organism`` itself if it is
    spelled ``seq:<genome>``."""
    if organism.startswith("seq:"):
        return organism[len("seq:") :]
    if organism not in organisms:
        raise KeyError(
            f"unknown organism {organism!r}: one of {sorted(organisms)}, "
            "or seq:<genome>"
        )
    return organisms[organism]


def make_dispatch(
    organism: str,
    *,
    policy: str = "hybrid",
    batch_size: int = 8,
    rel_tol: float = 0.02,
    search_seed: int | None = None,
    meta_seed: int | None = None,
    binary: str | None = None,
    config_dir: str | None = None,
    schedule: str = "* * * * *",
    orchestrator: str = "subprocess",
    max_procs: int = 8,
    trial_batchsize: int = 1,
    assay_kwargs: dict | None = None,
    num_control_trials: int = 40,
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
        "sequence": sequence_of(organism, organisms),
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
    kwargs.update(assay_kwargs or {})  # e.g. gama's population sizes
    d = {
        "meta_project": "default",
        "meta_experiment": "default",
        "meta_treatment": "default",
        "meta_user": subprocess.check_output(["id", "-un"], text=True).strip(),
        "meta_redo": "0",
        "assay": "scd.churn.seed_global_rngs("
        f"scd.assaylib.skeletonization.{policy}.make_churn("
        f"num_control_trials={int(num_control_trials)}))",
        "assay_kwargs": kwargs,
        "schedule": schedule,
        "trial_batchsize": trial_batchsize,
        "trial_batch_timeout": 600,
        # every hook is spelled out: none has a default
        "how_setup": "scd.record.appendjsonl.setup()",
        "how_read_trial_submissions": "scd.record.appendjsonl.read_trial_submissions()",
        "how_write_trial_submissions": "scd.record.appendjsonl.write_trial_submissions()",
        "how_read_trial_payloads": "scd.record.appendjsonl.read_trial_payloads()",
        "how_write_trial_payloads": "scd.record.appendjsonl.write_trial_payloads()",
        "how_prep_trial_payloads": "scd.record.appendjsonl.prep_trial_payloads()",
        "how_read_trial_telemetry": "scd.record.appendjsonl.read_trial_telemetry()",
        "how_write_trial_telemetry": "scd.record.appendjsonl.write_trial_telemetry()",
        "how_read_churn_memo": "scd.record.appendjsonl.read_churn_memo()",
        "how_write_churn_memo": "scd.record.appendjsonl.write_churn_memo()",
        "how_read_churn_notify": "scd.record.appendjsonl.read_churn_notify()",
        "how_write_churn_notify": "scd.record.appendjsonl.write_churn_notify()",
        "how_notify_progress": "scd.notify.log.notify()",
        "how_notify_eta": "scd.notify.log.notify()",
        "how_notify_success": "scd.notify.log.notify()",
        "how_notify_failure": "scd.notify.log.notify()",
        "how_notify_warning": "scd.notify.log.notify()",
        "how_notify_anomaly": "scd.notify.log.notify()",
        "how_unblock_churn": "scd.unblock.all_trials_ready()",
        "how_cleanup_success": "scd.cleanup.tar(clear=True)",
        "how_cleanup_failure": "lambda ctx, completed: None",
    }
    if meta_seed is not None:  # else submit_dispatch draws one
        d["meta_seed"] = meta_seed
    if orchestrator == "subprocess":
        d["how_launch"] = "scd.orch.subprocess.launch()"
        d["how_poke"] = "scd.orch.subprocess.poke()"
        d["how_kill"] = "scd.orch.subprocess.kill()"
        d[
            "how_throttle_churn"
        ] = f"scd.orch.subprocess.throttle(max_procs={max_procs})"
    elif orchestrator == "slurm":
        d["how_launch"] = "scd.orch.slurm.launch(sbatch_flags='--mem=1G')"
        d["how_poke"] = "scd.orch.slurm.poke()"
        d["how_kill"] = "scd.orch.slurm.kill()"
        d["how_throttle_churn"] = "scd.orch.slurm.throttle(max_jobs=500)"
    return d


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    p.add_argument("organism", help="name in organisms.json, or seq:<genome>")
    p.add_argument(
        "--policy",
        default="hybrid",
        choices=["ddmin", "minesweeper", "hybrid", "gama"],
    )
    p.add_argument(
        "--assay-kwargs",
        type=json.loads,
        default={},
        metavar="JSON",
        help="more assay_kwargs, e.g. '{\"mate_children\": 64}' for gama",
    )
    p.add_argument(
        "--num-control-trials",
        type=int,
        default=40,
        help="wildtype trials the scores are judged against (the Test "
        "CPU is deterministic, so these all agree and any loss counts)",
    )
    p.add_argument("--batch-size", type=int, default=8)
    p.add_argument("--rel-tol", type=float, default=0.02)
    p.add_argument("--search-seed", type=int, default=None)
    p.add_argument("--meta-seed", type=int, default=None)
    p.add_argument("--schedule", default="* * * * *")
    p.add_argument(
        "--orchestrator", default="subprocess", choices=["subprocess", "slurm"]
    )
    p.add_argument("--max-procs", type=int, default=8)
    p.add_argument("--trial-batchsize", type=int, default=1)
    a = p.parse_args()
    try:
        dispatch = make_dispatch(
            a.organism,
            policy=a.policy,
            batch_size=a.batch_size,
            rel_tol=a.rel_tol,
            search_seed=a.search_seed,
            meta_seed=a.meta_seed,
            schedule=a.schedule,
            orchestrator=a.orchestrator,
            max_procs=a.max_procs,
            trial_batchsize=a.trial_batchsize,
            assay_kwargs=a.assay_kwargs,
            num_control_trials=a.num_control_trials,
        )
    except KeyError as e:
        p.error(e.args[0])
    json.dump(dispatch, sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
