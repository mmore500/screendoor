from __future__ import annotations

import logging
import typing

if typing.TYPE_CHECKING:
    import datetime


def notify() -> typing.Callable[..., list[dict]]:
    """Log each notification via ``logging``.

    Returns
    -------
    Callable[..., list]
        The notifier: ``(ctx, level, message, data, history, now)`` logs
        ``message``, as a warning at failure, warning and anomaly, and
        returns a ``sent`` event.
    """

    def notify(
        ctx: dict,
        level: str,
        message: str,
        data: dict,
        history: list[dict],
        now: datetime.datetime,
    ) -> list[dict]:
        loud = level in ("failure", "warning", "anomaly")
        log = logging.warning if loud else logging.info
        log(
            "screendoor [%s] %s: %s",
            ctx.get("dispatch_uuid", "daemon")[:8],
            level,
            message,
        )
        return [{"event": "sent", "via": "log"}]

    return notify
