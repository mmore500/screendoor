from ..auxlib._next_cron_firing import next_cron_firing
from ..auxlib._now_iso import now


def next_firing(ctx):
    """When the dispatch is next due: at once if it has never ticked."""
    if ctx.last_tick is None:
        return now()
    return next_cron_firing(ctx.record["schedule"], ctx.last_tick)
