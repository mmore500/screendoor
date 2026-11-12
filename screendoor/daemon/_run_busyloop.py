import logging

from ..auxlib._now_iso import now, sleep
from ._notify_daemon import notify_daemon
from ._run_tick_once import next_firing, run_tick_once
from ._signals import STOP


def run_busyloop(workdir: str, *, max_ticks: int | None = None) -> None:
    """Tick, sleep until the next firing, repeat until none is active.

    Tells how_notify_termination why the daemon stopped, unless it was
    killed outright or reached ``max_ticks``.
    """
    try:
        _loop(workdir, max_ticks)
    except Exception as e:
        notify_daemon(workdir, "termination", f"daemon died: {e!r}")
        raise


def _loop(workdir: str, max_ticks: int | None) -> None:
    ticks = 0
    while True:
        if STOP["requested"]:
            notify_daemon(workdir, "termination", "daemon stopped on request")
            return
        active = run_tick_once(workdir)
        ticks += 1
        if not active:
            message = "daemon exited: no active dispatches"
            notify_daemon(workdir, "termination", message)
            return
        if ticks == max_ticks:
            return
        wake = min(map(next_firing, active))
        delay = max(0.0, (wake - now()).total_seconds())
        logging.info("screendoor: sleeping %.0fs until %s", delay, wake)
        sleep(delay + 0.5)
