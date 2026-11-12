import contextlib
import fcntl
import logging
import os

from ..auxlib._DispatchContext import load_dispatches
from ..auxlib._next_cron_firing import next_cron_firing
from ..auxlib._now_iso import now
from ._notify_daemon import notify_daemon
from ._signals import STOP
from ._tick import tick


@contextlib.contextmanager
def workdir_lock(workdir: str, *, wait: bool = False):
    """Yield whether this process got the workdir's exclusive lock.

    Keeps two local daemons from ticking at once. With ``wait``, block
    until the lock is free.
    """
    os.makedirs(workdir, exist_ok=True)
    with open(os.path.join(workdir, ".screendoor.lock"), "a") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
        except OSError:
            yield False
        else:
            yield True  # closing the file releases the lock


def next_firing(ctx):
    """When the dispatch is next due: at once if it has never ticked."""
    if ctx.last_tick is None:
        return now()
    return next_cron_firing(ctx.record["schedule"], ctx.last_tick)


def run_tick_once(workdir: str, *, force: bool = False) -> list:
    """Tick every due active dispatch once. Returns the active dispatches.

    Active means neither closed nor killed. Each pass pings
    how_notify_liveness.
    """
    with workdir_lock(workdir) as locked:
        if locked:
            notify_daemon(workdir, "liveness", "daemon pass")
        else:
            logging.info("screendoor: another daemon holds %s", workdir)
        for ctx in load_dispatches(workdir) if locked else ():
            if STOP["requested"]:
                logging.info("screendoor: stop requested; ending pass")
                break
            if not ctx.active or not (force or next_firing(ctx) <= now()):
                continue
            try:
                tick(ctx)
            except Exception:  # one dispatch failing never stops the others
                logging.exception(
                    "screendoor: tick of %s failed", ctx.dispatch_uuid
                )
        return [c for c in load_dispatches(workdir) if c.active]
