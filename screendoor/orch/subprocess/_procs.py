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


def live_pid(path: str) -> int | None:
    """The pid of the batch whose pidfile is ``path``, if it still runs."""
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
    return live_pid(path) is not None
