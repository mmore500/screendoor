import os
import shlex

from . import _run_slurm_command as _rsc
from ._render_sbatch import render_sbatch


def launch(
    *,
    sbatch_flags: str | list = "",
    worker: str = "python3 -m screendoor.trial.worker",
    script_dir: str = "~/slurmscripts",
    log_dir: str = "~/slurmlogs",
):
    """Submit one job's batches as one ``sbatch --array`` named for it.

    Array task i runs batch i, so a trial's job is its recorded name and
    index. ``sbatch_flags`` pass to sbatch verbatim, overriding the
    script's own ``#SBATCH`` lines. ``worker`` is the command that starts
    the worker.
    """
    if isinstance(sbatch_flags, str):
        sbatch_flags = shlex.split(sbatch_flags)

    def launch(ctx, name: str, batches: list) -> None:
        path = os.path.join(ctx.run_dir, "jobs", f"{name}.sbatch")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(
                render_sbatch(
                    ctx,
                    name,
                    batches,
                    worker=worker,
                    script_dir=script_dir,
                    log_dir=log_dir,
                )
            )
        _rsc.run(["sbatch", "--parsable", *sbatch_flags, path])

    return launch
