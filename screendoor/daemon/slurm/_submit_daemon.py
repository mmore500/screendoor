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
    dispatchdir: str,
    *,
    python: str | None = None,
    sbatch_flags: str = "",
    script_dir: str = "~/slurmscripts",
    log_dir: str = "~/slurmlogs",
    successor: bool = False,
) -> str | None:
    """Queue a daemon job for ``dispatchdir``; return its job id.

    Run this after submitting or resuming a dispatch: neither starts a
    daemon.

    The job is timed by ``--begin``: the earliest time an active dispatch
    is due. A ``successor``, queued by a daemon job before it ticks, begins
    when a dispatch is next due after that tick. Daemon jobs do not wait
    on each other; one that starts while another is ticking finds the
    dispatchdir lock held, skips its tick, and still queues its successor.

    Returns None, queueing nothing, when no dispatch is active or (unless
    ``successor``) a daemon job is already queued; that job is pulled
    forward instead.

    Parameters
    ----------
    dispatchdir : str
        The dispatchdir to run a daemon for.
    python : str or None, default None
        The command that runs python with screendoor importable; None for
        default_python_command.
    sbatch_flags : str, default ""
        Extra sbatch flags, as one shell string.
    script_dir : str, default "~/slurmscripts"
        Where the job keeps a copy of its script.
    log_dir : str, default "~/slurmlogs"
        Where the job writes its log.
    successor : bool, default False
        Whether a daemon job is queueing its successor.

    Returns
    -------
    str or None
        The queued job's id, or None if none was queued.
    """
    begin = earliest_begin(dispatchdir, successor=successor)
    if begin is None:
        logging.info("screendoor: no active dispatch; daemon chain ends")
        if successor:
            message = "daemon chain ended: no active dispatches"
            notify_daemon(dispatchdir, "termination", message)
        return None
    if not successor and pull_successor_forward(dispatchdir, begin):
        return None
    script = render_daemon_sbatch(
        dispatchdir,
        python=python or default_python_command(),
        sbatch_flags=sbatch_flags,
        script_dir=script_dir,
        log_dir=log_dir,
    )
    path = os.path.join(
        os.path.abspath(dispatchdir), "screendoor-daemon.sbatch"
    )
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


def cancel_chain(dispatchdir: str) -> None:
    """Cancel the queued daemon job if no dispatch is left active.

    A daemon job that is running finishes its tick, which does nothing.

    Parameters
    ----------
    dispatchdir : str
        The daemon's dispatchdir.
    """
    jobs = [jobid for jobid, _ in queued_chain_jobs(dispatchdir)]
    if jobs and earliest_begin(dispatchdir) is None:
        _rsc.run(["scancel", *jobs])
