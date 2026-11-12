from __future__ import annotations

import glob
import os
import typing

from ._procs import is_alive


def throttle(*, max_procs: int) -> typing.Callable[[dict], bool]:
    """Pass while fewer than ``max_procs`` local batches run in the dispatchdir.

    Parameters
    ----------
    max_procs : int
        Throttle once this many batches are running.

    Returns
    -------
    Callable[[dict], bool]
        The ``how_throttle_churn`` hook: ``(ctx)`` returns whether churn
        may run.
    """

    def throttle(ctx: dict) -> bool:
        pattern = os.path.join(ctx["dispatchdir"], "*", "jobs", "*", "*.pid")
        return sum(map(is_alive, glob.glob(pattern))) < max_procs

    return throttle
