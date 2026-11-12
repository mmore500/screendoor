import os


def launch_dir(ctx, launch_id: str) -> str:
    return os.path.join(ctx.run_dir, "launches", launch_id)


def _starttime(pid: int) -> str | None:
    """The process's start time from /proc; None if gone or a zombie."""
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as fh:
            stat = fh.read()
    except OSError:
        return None
    fields = stat[stat.rfind(")") + 2 :].split()  # the fields after comm
    return None if fields[0] == "Z" else fields[19]


def is_alive(job_id: str) -> bool:
    _, pid, start = job_id.split(":", 2)
    if os.path.isdir("/proc"):
        return _starttime(int(pid)) == start
    try:  # pragma: no cover - non-Linux fallback
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    return True


def read_pidfile(path: str) -> str | None:
    """A job id, ``pid:<pid>:<start time>``; None if there is no pid yet.

    The start time tells the process apart from a later one that reuses
    its pid.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            pid = int(fh.read())
    except (OSError, ValueError):
        return None
    start = _starttime(pid) if os.path.isdir("/proc") else "0"
    return f"pid:{pid}:{start or 'exited'}"
