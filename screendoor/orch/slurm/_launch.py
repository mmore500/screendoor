import os
import shlex
import typing

from . import _run_slurm_command as _rsc
from ._render_sbatch import render_sbatch


def launch(
    *,
    sbatch_flags: str | list[str] = "",
    worker: str = "python3 -m screendoor.trial.worker",
    script_dir: str = "~/slurmscripts",
    log_dir: str = "~/slurmlogs",
) -> typing.Callable[[dict, str, list[list[dict]]], None]:
    """Create a `how_launch` hook that submits each job's batches as one
    `sbatch --array` named for the job.

    Array task `i` runs batch `i`, so a trial's job is its recorded name
    and index.

    Parameters
    ----------
    sbatch_flags : str or list of str, default ""
        Extra flags passed to `sbatch` verbatim, overriding the script's
        own `#SBATCH` lines; a string is split as the shell would.
    worker : str, default "python3 -m screendoor.trial.worker"
        The command that starts the worker on the compute node, where this
        interpreter may not exist.
    script_dir : str, default "~/slurmscripts"
        Where each job keeps a copy of its script.
    log_dir : str, default "~/slurmlogs"
        Where each job keeps its log.

    Returns
    -------
    Callable[[dict, str, list[list[dict]]], None]
        Hook `launch(ctx, name, batches)`, which writes the job's script to
        `jobs/<name>.sbatch` in the run directory and submits it.
    """
    if isinstance(sbatch_flags, str):
        sbatch_flags = shlex.split(sbatch_flags)

    def launch(ctx: dict, name: str, batches: list[list[dict]]) -> None:
        path = os.path.join(ctx["run_dir"], "jobs", f"{name}.sbatch")
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
