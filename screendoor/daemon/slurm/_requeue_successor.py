import datetime

from ...auxlib._DispatchContext import load_dispatches
from ...auxlib._next_cron_firing import next_cron_firing
from ...auxlib._now_iso import now
from ...orch.slurm import _run_slurm_command as _rsc
from .._next_firing import next_firing
from ._render_daemon_sbatch import chain_job_name


def queued_chain_jobs(dispatchdir: str) -> list[tuple[str, str]]:
    """List the pending daemon jobs of `dispatchdir`.

    Parameters
    ----------
    dispatchdir : str
        Path of the daemon's dispatchdir.

    Returns
    -------
    list of tuple of (str, str)
        One `(job id, start time)` pair per pending job, as `squeue` prints
        them.
    """
    out = _rsc.run(
        [
            "squeue",
            "--me",
            "--noheader",
            "--states=PENDING",
            f"--name={chain_job_name(dispatchdir)}",
            "--format=%i|%S",
        ]
    )
    return [tuple(line.split("|", 1)) for line in out.split()]


def earliest_begin(
    dispatchdir: str, *, successor: bool = False
) -> datetime.datetime | None:
    """Find the earliest time an active dispatch of `dispatchdir` is next
    due.

    With `successor`, a dispatch due now counts at its following cron
    firing instead: the daemon job queueing the successor is about to tick
    it, so the successor's `--begin` is when the dispatch is next due after
    that.

    Parameters
    ----------
    dispatchdir : str
        Path of the dispatchdir.
    successor : bool, default False
        Whether the time is the `--begin` of a successor job.

    Returns
    -------
    datetime.datetime or None
        The firing, no earlier than now; None if no dispatch is active.
    """
    t = now()
    firings = []
    for c in load_dispatches(dispatchdir):
        if not c.active:
            continue
        firing = next_firing(c)
        if successor and firing <= now():  # due: the caller ticks it now
            firing = next_cron_firing(c.record["schedule"], t)
        firings.append(firing)
    return max(min(firings), t) if firings else None


def slurm_time(dt: datetime.datetime) -> str:
    """Format `dt` as Slurm takes a time, `YYYY-MM-DDTHH:MM:SS` in local
    time.

    Parameters
    ----------
    dt : datetime.datetime
        A timezone-aware time.

    Returns
    -------
    str
        The formatted time.
    """
    return dt.astimezone().strftime("%Y-%m-%dT%H:%M:%S")


def pull_successor_forward(dispatchdir: str, begin: datetime.datetime) -> bool:
    """Move the start of any pending daemon job of `dispatchdir` up to
    `begin`.

    Parameters
    ----------
    dispatchdir : str
        Path of the daemon's dispatchdir.
    begin : datetime.datetime
        The latest start to allow.

    Returns
    -------
    bool
        Whether any daemon job was pending.
    """
    jobs = queued_chain_jobs(dispatchdir)
    for jobid, start in jobs:
        try:
            if datetime.datetime.fromisoformat(start).astimezone() <= begin:
                continue
        except ValueError:  # squeue prints N/A when it has no start time
            pass
        _rsc.run(
            [
                "scontrol",
                "update",
                f"JobId={jobid}",
                f"StartTime={slurm_time(begin)}",
            ]
        )
    return bool(jobs)
