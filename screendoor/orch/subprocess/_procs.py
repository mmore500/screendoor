import os


def job_dir(ctx: dict, name: str) -> str:
    """Return the directory in which a job's batches keep their pidfiles
    and logs, `jobs/<name>` in the run directory.

    Parameters
    ----------
    ctx : dict
        The hook context of the dispatch the job belongs to.
    name : str
        The job name.

    Returns
    -------
    str
        The directory's path.
    """
    return os.path.join(ctx["run_dir"], "jobs", name)


def pidfile(ctx: dict, job: dict) -> str:
    """Return the pidfile of one batch of a job, `jobs/<name>/<index>.pid`
    in the run directory.

    Parameters
    ----------
    ctx : dict
        The hook context of the dispatch the job belongs to.
    job : dict
        A trial's recorded job, with `name` and `index`.

    Returns
    -------
    str
        The pidfile's path.
    """
    return os.path.join(job_dir(ctx, job["name"]), f"{job['index']}.pid")


def _starttime(pid: int) -> str | None:
    """Read a process's start time from /proc; None if it is gone or a
    zombie."""
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as fh:
            stat = fh.read()
    except OSError:
        return None
    fields = stat[stat.rfind(")") + 2 :].split()  # the fields after comm
    return None if fields[0] == "Z" else fields[19]


def read_pidfile(path: str) -> tuple[int, str] | None:
    """Read a batch's pidfile.

    The pidfile holds the pid and the process's start time, written as the
    batch starts, so that a later process that reuses the pid is not taken
    for the batch.

    Parameters
    ----------
    path : str
        The pidfile.

    Returns
    -------
    tuple of (int, str) or None
        The pid and its start time, or None if there is no pid yet.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            pid, _, start = fh.read().strip().partition(" ")
        return int(pid), start
    except (OSError, ValueError):
        return None


def live_pid(path: str) -> int | None:
    """Return the pid of the batch whose pidfile is `path`, if it still
    runs.

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
    """Is the batch whose pidfile is `path` still running?

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
