import datetime

from ..auxlib._DispatchContext import DispatchContext
from ..auxlib._next_cron_firing import next_cron_firing
from ..auxlib._now_iso import now


def next_firing(ctx: DispatchContext) -> datetime.datetime:
    """Return when the dispatch is next due: the first firing of its
    `schedule` after its last tick, or now if it has never ticked.

    Parameters
    ----------
    ctx : DispatchContext
        The dispatch.

    Returns
    -------
    datetime.datetime
        The time the dispatch is next due.
    """
    if ctx.last_tick is None:
        return now()
    return next_cron_firing(ctx.record["schedule"], ctx.last_tick)
