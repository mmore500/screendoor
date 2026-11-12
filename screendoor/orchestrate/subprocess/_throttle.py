import glob
import os

from ._procs import is_alive, read_pidfile


def throttle(*, max_procs: int):
    """Pass while fewer than ``max_procs`` local batches run in the workdir."""

    def throttle(ctx) -> bool:
        pidfiles = glob.glob(
            os.path.join(ctx.workdir, "*", "launches", "*", "*.pid")
        )
        jobs = filter(None, map(read_pidfile, pidfiles))
        return sum(map(is_alive, jobs)) < max_procs

    return throttle
