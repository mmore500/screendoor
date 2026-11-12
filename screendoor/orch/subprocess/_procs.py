from __future__ import annotations

import os


def job_dir(ctx: dict, name: str) -> str:
    """Where a job's batches keep their pidfiles and logs.

    Parameters
    ----------
    ctx : dict
        The dispatch the job belongs to.
    name : str
        The job name.

    Returns
    -------
    str
        ``jobs/<name>`` in the run directory.
    """
    return os.path.join(ctx["run_dir"], "jobs", name)


def pidfile(ctx: dict, job: dict) -> str:
    """The pidfile of one batch of a job.

    Parameters
    ----------
    ctx : dict
        The dispatch the job belongs to.
    job : dict
        A trial's recorded job: ``name`` and ``index``.

    Returns
    -------
    str
        ``jobs/<name>/<index>.pid`` in the run directory.
    """
    return os.path.join(job_dir(ctx, job["name"]), f"{job['index']}.pid")


def _starttime(pid: int) -> str | None:
    """The process's start time from /proc; None if gone or a zombie."""
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as fh:
            stat = fh.read()
    except OSError:
        return None
    fields = stat[stat.rfind(")") + 2 :].split()  # the fields after comm
    return None if fields[0] == "Z" else fields[19]


def read_pidfile(path: str) -> tuple[int, str] | None:
    """``(pid, start time)``; None if there is no pid yet.

    The pidfile holds both, written as the batch starts, so that a later
    process that reuses the pid is not taken for the batch.

    Parameters
    ----------
    path : str
        The pidfile.

    Returns
    -------
    tuple of (int, str) or None
        The pid and its start time, or None.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            pid, _, start = fh.read().strip().partition(" ")
        return int(pid), start
    except (OSError, ValueError):
        return None


def live_pid(path: str) -> int | None:
    """The pid of the batch whose pidfile is ``path``, if it still runs.

    Parameters
    ----------
    path : str
        The batch's pidfile.

    Returns
    -------
    int or None
        The pid, or None if the batch is not running.
    """
    found = read_pidfile(path)
    if found is None:
        return None
    pid, start = found
    if os.path.isdir("/proc"):
        return pid if _starttime(pid) == start else None
    try:  # pragma: no cover - non-Linux fallback
        os.kill(pid, 0)
    except ProcessLookupError:
        return None
    except PermissionError:
        pass
    return pid


def is_alive(path: str) -> bool:
    """Whether the batch whose pidfile is ``path`` still runs.

    Parameters
    ----------
    path : str
        The batch's pidfile.

    Returns
    -------
    bool
        True if the batch is running.
    """
    return live_pid(path) is not None
