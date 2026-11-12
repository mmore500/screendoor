from __future__ import annotations

import typing

from ..auxlib._next_cron_firing import next_cron_firing
from ..auxlib._now_iso import now

if typing.TYPE_CHECKING:
    import datetime

    from ..auxlib._DispatchContext import DispatchContext


def next_firing(ctx: DispatchContext) -> datetime.datetime:
    """When the dispatch is next due: at once if it has never ticked.

    Parameters
    ----------
    ctx : DispatchContext
        The dispatch.

    Returns
    -------
    datetime.datetime
        The first firing of its ``schedule`` after its last tick, or now.
    """
    if ctx.last_tick is None:
        return now()
    return next_cron_firing(ctx.record["schedule"], ctx.last_tick)
