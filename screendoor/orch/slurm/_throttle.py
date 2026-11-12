from __future__ import annotations

import logging
import typing

from . import _run_slurm_command as _rsc


def throttle(*, max_jobs: int) -> typing.Callable[[dict], bool]:
    """Pass while fewer than ``max_jobs`` of your jobs are queued or
    running, counting each array task, of any job, as one.

    Parameters
    ----------
    max_jobs : int
        Throttle once this many of your jobs are queued or running.

    Returns
    -------
    Callable[[dict], bool]
        The ``how_throttle_churn`` hook: ``(ctx)`` returns whether churn
        may run; False if ``squeue`` fails.
    """

    def throttle(ctx: dict) -> bool:
        try:
            return len(_rsc.queued_jobs()) < max_jobs
        except RuntimeError as e:
            logging.warning("screendoor: squeue failed, throttling: %s", e)
            return False

    return throttle
