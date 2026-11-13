import glob
import os
import typing

from ._procs import is_alive


def throttle(*, max_procs: int) -> typing.Callable[[dict], bool]:
    """Create a `how_throttle_churn` hook that lets churn run while fewer
    than `max_procs` batches are running across the dispatchdir.

    Running batches are counted by their live pidfiles, `jobs/<name>/<i>.pid`
    in every dispatch's run directory.

    Parameters
    ----------
    max_procs : int
        The number of running batches at which churn is throttled.

    Returns
    -------
    Callable[[dict], bool]
        Hook `throttle(ctx)`, returning whether churn may run.
    """

    def throttle(ctx: dict) -> bool:
        # run directories are <dispatchdir>/project=<p>/date=<d>+...
        pattern = os.path.join(
            ctx["dispatchdir"], "*", "*", "jobs", "*", "*.pid"
        )
        return sum(map(is_alive, glob.glob(pattern))) < max_procs

    return throttle
