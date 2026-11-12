import logging

from ..auxlib._now_iso import now, sleep
from ._next_firing import next_firing
from ._notify_daemon import notify_daemon
from ._run_tick_once import run_tick_once
from ._signals import STOP


def run_busyloop(dispatchdir: str, *, max_ticks: int | None = None) -> None:
    """Tick, sleep until the next firing, repeat until none is active.

    Tells how_notify_termination why the daemon stopped, unless it was
    killed outright or reached ``max_ticks``.
    """
    try:
        _loop(dispatchdir, max_ticks)
    except Exception as e:
        notify_daemon(dispatchdir, "termination", f"daemon died: {e!r}")
        raise


def _loop(dispatchdir: str, max_ticks: int | None) -> None:
    ticks = 0
    while True:
        if STOP["requested"]:
            notify_daemon(
                dispatchdir, "termination", "daemon stopped on request"
            )
            return
        active = run_tick_once(dispatchdir)
        ticks += 1
        if not active:
            message = "daemon exited: no active dispatches"
            notify_daemon(dispatchdir, "termination", message)
            return
        if ticks == max_ticks:
            return
        wake = min(map(next_firing, active))
        delay = max(0.0, (wake - now()).total_seconds())
        logging.info("screendoor: sleeping %.0fs until %s", delay, wake)
        sleep(delay + 0.5)
