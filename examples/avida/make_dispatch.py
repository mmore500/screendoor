#!/usr/bin/env python3
"""Print a screendoor dispatch (JSON) that skeletonizes an Avida organism.

    python3 make_dispatch.py nand_50 --policy hybrid \\
      | python3 -m screendoor.daemon.submit_dispatch - --dispatchdir work

Each trial scores one knockout with avida_fitness.py, which runs Avida in
the devosoft/avida container through singularity. A knockout is accepted if
it is viable, keeps every wildtype task and keeps fitness within rel_tol of
the wildtype's.
"""

import argparse
import getpass
import json
import os
import shlex
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
IMAGE = "docker://ghcr.io/devosoft/avida:latest"
POLICIES = ("ddmin", "minesweeper", "hybrid", "gama")


def sequence_of(organism: str, organisms: dict) -> str:
    """Look up the genome named `organism`, or take `seq:<genome>` as is."""
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
    image: str = IMAGE,
    batch_size: int = 8,
    rel_tol: float = 0.02,
    num_control_trials: int = 40,
    search_seed: int | None = None,
    meta_seed: int | None = None,
    schedule: str = "* * * * *",
    orchestrator: str = "subprocess",
    max_procs: int = 8,
    trial_batchsize: int = 1,
    assay_kwargs: dict | None = None,
) -> dict:
    """Build a dispatch that skeletonizes `organism` with `policy`.

    Parameters
    ----------
    organism : str
        A name in organisms.json, or `seq:<genome>`.
    policy : str, default "hybrid"
        One of `POLICIES`.
    image : str, default IMAGE
        The Avida container, as `singularity exec` takes it.
    batch_size : int, default 8
        Candidate knockouts per wave.
    rel_tol : float, default 0.02
        The fitness loss tolerated, as a fraction of the wildtype's.
    num_control_trials : int, default 40
        How many times the wildtype runs as a control.
    search_seed : int or None, default None
        Seed of the search; None uses the dispatch's `meta_seed`.
    meta_seed : int or None, default None
        The dispatch's seed; None lets `submit_dispatch` draw one.
    schedule : str, default "* * * * *"
        The dispatch's cron schedule.
    orchestrator : str, default "subprocess"
        `subprocess` or `slurm`.
    max_procs : int, default 8
        Local batches to run at once, with `subprocess`.
    trial_batchsize : int, default 1
        Trials per job.
    assay_kwargs : dict or None, default None
        Further assay kwargs, such as gama's population sizes.

    Returns
    -------
    dict
        The dispatch, as `submit_dispatch` takes it.
    """
    with open(os.path.join(HERE, "organisms.json")) as fh:
        organisms = json.load(fh)
    script = shlex.quote(os.path.join(HERE, "avida_fitness.py"))
    kwargs = {
        "sequence": sequence_of(organism, organisms),
        "nop_symbol": "A",
        "cmd": f'set -euo pipefail\npython3 {script} "$sequence"\n',
        "batch_size": batch_size,
        "rel_tol": rel_tol,
        "require_atleast": ["tasks"],
        "env": {"AVIDA_IMAGE": image},
    }
    if search_seed is not None:
        kwargs["search_seed"] = search_seed
    kwargs.update(assay_kwargs or {})
    assay = (
        "scd.churn.seed_global_rngs("
        f"scd.assaylib.skeletonization.{policy}.make_churn("
        f"num_control_trials={int(num_control_trials)}))"
    )
    orch = f"scd.orch.{orchestrator}"
    launch, throttle = {
        "subprocess": (
            f"{orch}.launch()",
            f"{orch}.throttle(max_procs={max_procs})",
        ),
        "slurm": (
            f"{orch}.launch(sbatch_flags='--mem=1G')",
            f"{orch}.throttle(max_jobs=500)",
        ),
    }[orchestrator]
    dispatch = {
        "meta_project": "avida",
        "meta_experiment": "seq" if organism.startswith("seq:") else organism,
        "meta_treatment": policy,
        "meta_user": getpass.getuser(),
        "meta_redo": "0",
        "assay": assay,
        "assay_kwargs": kwargs,
        "schedule": schedule,
        "trial_batchsize": trial_batchsize,
        "trial_batch_timeout": 600,
        # every hook is spelled out: none has a default
        "how_launch": launch,
        "how_poke": f"{orch}.poke()",
        "how_kill": f"{orch}.kill()",
        "how_throttle_churn": throttle,
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
    if meta_seed is not None:
        dispatch["meta_seed"] = meta_seed
    return dispatch


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "organism", help="name in organisms.json, or seq:<genome>"
    )
    parser.add_argument("--policy", default="hybrid", choices=POLICIES)
    parser.add_argument(
        "--image",
        default=IMAGE,
        help="the Avida container, as singularity exec takes it "
        "(default: %(default)s)",
    )
    parser.add_argument(
        "--assay-kwargs",
        type=json.loads,
        default={},
        metavar="JSON",
        help="more assay_kwargs, e.g. '{\"mate_children\": 64}' for gama",
    )
    parser.add_argument(
        "--num-control-trials",
        type=int,
        default=40,
        help="wildtype trials the scores are judged against (the Test "
        "CPU is deterministic, so these all agree and any loss counts)",
    )
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--rel-tol", type=float, default=0.02)
    parser.add_argument("--search-seed", type=int)
    parser.add_argument("--meta-seed", type=int)
    parser.add_argument("--schedule", default="* * * * *")
    parser.add_argument(
        "--orchestrator", default="subprocess", choices=["subprocess", "slurm"]
    )
    parser.add_argument("--max-procs", type=int, default=8)
    parser.add_argument("--trial-batchsize", type=int, default=1)
    args = vars(parser.parse_args())
    try:
        dispatch = make_dispatch(args.pop("organism"), **args)
    except KeyError as e:
        parser.error(e.args[0])
    json.dump(dispatch, sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
