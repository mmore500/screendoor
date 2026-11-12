import contextlib
import os
import signal

from ._procs import live_pid, pidfile


def kill():
    """Send SIGTERM to the process group of each trial's batch."""

    def kill(ctx, trials: list) -> None:
        paths = {pidfile(ctx, t["job"]) for t in trials if t["job"]}
        for path in sorted(paths):
            pid = live_pid(path)
            if pid is None:
                continue
            with contextlib.suppress(ProcessLookupError):
                group = os.getpgid(pid)
                if group == os.getpgid(0):  # never signal our own group
                    os.kill(pid, signal.SIGTERM)
                else:
                    os.killpg(group, signal.SIGTERM)

    return kill
