import datetime

from ...auxlib._DispatchContext import load_dispatches
from ...auxlib._now_iso import now
from ...orch.slurm import _run_slurm_command as _rsc
from .._run_tick_once import next_firing
from ._render_daemon_sbatch import chain_job_name


def queued_chain_jobs(workdir: str) -> list:
    """Pending daemon jobs, as ``(jobid, start time)`` string pairs."""
    out = _rsc.run(
        [
            "squeue",
            "--me",
            "--noheader",
            "--states=PENDING",
            f"--name={chain_job_name(workdir)}",
            "--format=%i|%S",
        ]
    )
    return [tuple(line.split("|", 1)) for line in out.split()]


def earliest_begin(workdir: str) -> datetime.datetime | None:
    """Earliest next firing over active dispatches; None if there are none."""
    firings = [next_firing(c) for c in load_dispatches(workdir) if c.active]
    return max(min(firings), now()) if firings else None


def slurm_time(dt: datetime.datetime) -> str:
    return dt.astimezone().strftime("%Y-%m-%dT%H:%M:%S")


def pull_successor_forward(workdir: str, begin: datetime.datetime) -> bool:
    """Move pending daemon jobs' start up to ``begin``; False if none."""
    jobs = queued_chain_jobs(workdir)
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
