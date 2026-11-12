import os


def job_dir(ctx, name: str) -> str:
    """Where a job's batches keep their pidfiles and logs."""
    return os.path.join(ctx.run_dir, "jobs", name)


def pidfile(ctx, job: dict) -> str:
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


def read_pidfile(path: str) -> tuple | None:
    """``(pid, start time)``; None if there is no pid yet.

    The pidfile holds both, written as the batch starts, so that a later
    process that reuses the pid is not taken for the batch.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            pid, _, start = fh.read().strip().partition(" ")
        return int(pid), start
    except (OSError, ValueError):
        return None


def is_alive(path: str) -> bool:
    """Whether the batch whose pidfile is ``path`` is still running."""
    found = read_pidfile(path)
    if found is None:
        return False
    pid, start = found
    if os.path.isdir("/proc"):
        return _starttime(pid) == start
    try:  # pragma: no cover - non-Linux fallback
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    return True
