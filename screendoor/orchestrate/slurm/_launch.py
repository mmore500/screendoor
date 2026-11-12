import os
import shlex

from . import _run_slurm_command as _rsc
from ...auxlib._batch_trials import batch_trials
from ._render_sbatch import job_name, parse_batches, render_sbatch


def launch(
    *,
    sbatch_flags: str | list = "",
    worker: str = "python3 -m screendoor.worker",
    script_dir: str = "~/slurmscripts",
    log_dir: str = "~/slurmlogs",
):
    """Submit the batches of one launch call as one ``sbatch --array``.

    ``sbatch_flags`` pass to sbatch verbatim, overriding the script's own
    ``#SBATCH`` lines. ``worker`` is the command that starts the worker.
    """
    if isinstance(sbatch_flags, str):
        sbatch_flags = shlex.split(sbatch_flags)

    def script_path(ctx, launch_id: str) -> str:
        return os.path.join(ctx.run_dir, "launches", f"{launch_id}.sbatch")

    def launch(ctx, entries: list, launch_id: str) -> list:
        batches = batch_trials(entries, ctx.record["trial_batchsize"])
        path = script_path(ctx, launch_id)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(
                render_sbatch(
                    ctx,
                    batches,
                    launch_id,
                    worker=worker,
                    script_dir=script_dir,
                    log_dir=log_dir,
                )
            )
        out = _rsc.run(["sbatch", "--parsable", *sbatch_flags, path])
        jobid = out.strip().split(";")[0]
        return [
            {**e, "job_id": f"{jobid}_{i}"}
            for i, batch in enumerate(batches)
            for e in batch
        ]

    def adopt(ctx, launch_id: str, entries: list) -> dict:
        """Find jobs an interrupted launch call already submitted.

        Returns ``{(trial_uuid, attempt): job_id}``.
        """
        try:
            with open(script_path(ctx, launch_id), encoding="utf-8") as fh:
                batches = parse_batches(fh.read()) or []
            name = f"--name={job_name(launch_id)}"
            jobs = (
                _rsc.run(
                    [
                        "squeue",
                        "--me",
                        "--noheader",
                        "--array",
                        name,
                        "--format=%i",
                    ]
                ).split()
                + _rsc.run(
                    [
                        "sacct",
                        "--noheader",
                        "--parsable2",
                        "--allocations",
                        name,
                        "--starttime=now-14days",
                        "--format=JobID",
                    ]
                ).split()
            )
        except (OSError, RuntimeError):
            return {}
        found = {}
        for job in jobs:
            task = job.partition("_")[2]
            if task.isdigit() and int(task) < len(batches):
                for e in batches[int(task)]:
                    found[e["trial_uuid"], e["attempt"]] = job
        return found

    launch.adopt = adopt
    return launch
