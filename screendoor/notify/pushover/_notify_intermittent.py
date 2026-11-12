from __future__ import annotations

import typing

from ...auxlib._now_iso import parse_iso
from ._send import send

if typing.TYPE_CHECKING:
    import datetime


def notify_intermittent(
    *, interval_s: float = 3600
) -> typing.Callable[..., list[dict]]:
    """Send if the last send is older than ``interval_s``; else suppress.

    Parameters
    ----------
    interval_s : float, default 3600
        Seconds to wait after a send before sending again.

    Returns
    -------
    Callable[..., list]
        The notifier: ``(ctx, level, message, data, history, now)`` sends
        ``message``, or suppresses it, and returns its event.
    """

    def notify(
        ctx: dict,
        level: str,
        message: str,
        data: dict,
        history: list[dict],
        now: datetime.datetime,
    ) -> list[dict]:
        sends = [parse_iso(h["ts"]) for h in history if h["event"] == "sent"]
        if sends and (now - max(sends)).total_seconds() < interval_s:
            return [
                {
                    "event": "suppressed",
                    "reason": "interval",
                    "message": message,
                }
            ]
        return [send(ctx, level, message)]

    return notify
