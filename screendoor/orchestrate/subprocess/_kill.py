import contextlib
import os
import signal

from ._procs import is_alive


def kill():
    """Send SIGTERM to the process group of each trial's batch."""

    def kill(ctx, trials: list) -> None:
        for job in {t["job_id"] for t in trials}:
            if not (job and job.startswith("pid:") and is_alive(job)):
                continue
            pid = int(job.split(":")[1])
            with contextlib.suppress(ProcessLookupError):
                group = os.getpgid(pid)
                if group == os.getpgid(0):  # never signal our own group
                    os.kill(pid, signal.SIGTERM)
                else:
                    os.killpg(group, signal.SIGTERM)

    return kill
