from ...auxlib._now_iso import parse_iso
from ._send import send


def notify_intermittent(*, interval_s: float = 3600):
    """Send if the last send is older than ``interval_s``; else suppress."""

    def notify(ctx, level, message, data, history, now) -> list:
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
