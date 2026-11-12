from __future__ import annotations

import logging
import typing

from ..auxlib._DispatchContext import load_dispatches
from ..auxlib._now_iso import now
from ._dispatchdir_lock import dispatchdir_lock
from ._next_firing import next_firing
from ._notify_daemon import notify_daemon
from ._signals import STOP
from ._tick import tick

if typing.TYPE_CHECKING:
    from ..auxlib._DispatchContext import DispatchContext


def run_tick_once(
    dispatchdir: str, *, force: bool = False
) -> list[DispatchContext]:
    """Tick every due active dispatch once. Returns the active dispatches.

    Active means neither completed nor killed. Each pass pings
    how_notify_liveness.

    Parameters
    ----------
    dispatchdir : str
        The dispatchdir to tick.
    force : bool, default False
        Tick active dispatches even if not yet due.

    Returns
    -------
    list of DispatchContext
        The dispatches still active after the pass, reloaded.
    """
    with dispatchdir_lock(dispatchdir) as locked:
        if locked:
            notify_daemon(dispatchdir, "liveness", "daemon pass")
        else:
            logging.info("screendoor: another daemon holds %s", dispatchdir)
        for ctx in load_dispatches(dispatchdir) if locked else ():
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
        return [c for c in load_dispatches(dispatchdir) if c.active]
