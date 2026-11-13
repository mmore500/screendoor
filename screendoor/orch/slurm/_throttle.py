import logging
import typing

from . import _run_slurm_command as _rsc


def throttle(*, max_jobs: int) -> typing.Callable[[dict], bool]:
    """Create a `how_throttle_churn` hook that lets churn run while fewer
    than `max_jobs` of the user's jobs are queued or running, counting each
    array task of any job as one.

    Parameters
    ----------
    max_jobs : int
        The number of jobs at which churn is throttled.

    Returns
    -------
    Callable[[dict], bool]
        Hook `throttle(ctx)`, returning whether churn may run; False if
        `squeue` fails.
    """

    def throttle(ctx: dict) -> bool:
        try:
            return len(_rsc.queued_jobs()) < max_jobs
        except RuntimeError as e:
            logging.warning("screendoor: squeue failed, throttling: %s", e)
            return False

    return throttle
