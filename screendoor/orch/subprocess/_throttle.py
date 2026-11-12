import glob
import os

from ._procs import is_alive


def throttle(*, max_procs: int):
    """Pass while fewer than ``max_procs`` local batches run in the dispatchdir."""

    def throttle(ctx) -> bool:
        pattern = os.path.join(ctx.dispatchdir, "*", "jobs", "*", "*.pid")
        return sum(map(is_alive, glob.glob(pattern))) < max_procs

    return throttle
