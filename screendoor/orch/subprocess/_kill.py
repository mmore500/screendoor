from __future__ import annotations

import contextlib
import os
import signal
import typing

from ._procs import live_pid, pidfile


def kill() -> typing.Callable[[dict, list[dict]], None]:
    """Send SIGTERM to the process group of each trial's batch.

    Returns
    -------
    Callable[[dict, list], None]
        The ``how_kill`` hook: ``(ctx, trials)`` signals each running
        batch the trials belong to.
    """

    def kill(ctx: dict, trials: list[dict]) -> None:
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
