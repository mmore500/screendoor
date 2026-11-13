import datetime
import logging
import typing


def notify() -> typing.Callable[..., list[dict]]:
    """Create a notifier that logs each notification through `logging`.

    Returns
    -------
    Callable[..., list[dict]]
        Notifier `notify(ctx, level, message, data, history, now)`, which
        logs `message` (as a warning at the `failure`, `warning` and
        `anomaly` levels, else as info) and returns a `sent` event.
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
