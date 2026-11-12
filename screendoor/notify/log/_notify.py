import logging


def notify():
    """Log each notification via ``logging``."""

    def notify(ctx, level, message, data, history, now) -> list:
        loud = level in ("failure", "warning", "anomaly")
        log = logging.warning if loud else logging.info
        log("screendoor [%s] %s: %s", ctx.dispatch_uuid[:8], level, message)
        return [{"event": "sent", "via": "log"}]

    return notify
