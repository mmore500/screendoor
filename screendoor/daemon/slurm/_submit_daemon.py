import logging
import os
import shlex

from ...auxlib._default_python_command import default_python_command
from ...orch.slurm import _run_slurm_command as _rsc
from .._notify_daemon import notify_daemon
from ._render_daemon_sbatch import render_daemon_sbatch
from ._requeue_successor import (
    earliest_begin,
    pull_successor_forward,
    queued_chain_jobs,
    slurm_time,
)


def submit_daemon(
    workdir: str,
    *,
    python: str | None = None,
    sbatch_flags: str = "",
    script_dir: str = "~/slurmscripts",
    log_dir: str = "~/slurmlogs",
    successor: bool = False,
) -> str | None:
    """Queue a daemon job for ``workdir``; return its job id.

    Run this after submitting or resuming a dispatch: neither starts a
    daemon.

    Returns None, queueing nothing, when no dispatch is active or (unless
    ``successor``) a daemon job is already queued; that job is pulled
    forward instead.
    """
    begin = earliest_begin(workdir)
    if begin is None:
        logging.info("screendoor: no active dispatch; daemon chain ends")
        if successor:
            message = "daemon chain ended: no active dispatches"
            notify_daemon(workdir, "termination", message)
        return None
    if not successor and pull_successor_forward(workdir, begin):
        return None
    script = render_daemon_sbatch(
        workdir,
        python=python or default_python_command(),
        sbatch_flags=sbatch_flags,
        script_dir=script_dir,
        log_dir=log_dir,
    )
    path = os.path.join(os.path.abspath(workdir), "screendoor-daemon.sbatch")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(script)
    out = _rsc.run(
        [
            "sbatch",
            "--parsable",
            f"--begin={slurm_time(begin)}",
            *shlex.split(sbatch_flags),
            path,
        ]
    )
    return out.strip().split(";")[0]


def cancel_chain(workdir: str) -> None:
    """Cancel the queued daemon job if no dispatch is left active.

    A daemon job that is running finishes its tick, which does nothing.
    """
    jobs = [jobid for jobid, _ in queued_chain_jobs(workdir)]
    if jobs and earliest_begin(workdir) is None:
        _rsc.run(["scancel", *jobs])
