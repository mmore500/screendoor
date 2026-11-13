import datetime
import typing

from ...auxlib._now_iso import parse_iso
from ._send import send


def notify_batched(
    *, interval_s: float = 3600
) -> typing.Callable[..., list[dict]]:
    """Create a notifier that queues notifications and sends one digest per
    `interval_s` seconds.

    The digest groups repeats that share a `dedupe_key`. Messages held by a
    digest whose send failed go out with the next one.

    Parameters
    ----------
    interval_s : float, default 3600
        Seconds between digests.

    Returns
    -------
    Callable[..., list[dict]]
        Notifier `notify(ctx, level, message, data, history, now)`,
        returning a `queued` event. Its `flush(ctx, level, history, now)`
        sends what was queued since the last digest that got through, at
        most once per `interval_s`, and returns the digest's event.
    """

    def notify(
        ctx: dict,
        level: str,
        message: str,
        data: dict,
        history: list[dict],
        now: datetime.datetime,
    ) -> list[dict]:
        key = data.get("dedupe_key", message)
        return [{"event": "queued", "message": message, "dedupe_key": key}]

    def flush(
        ctx: dict,
        level: str,
        history: list[dict],
        now: datetime.datetime,
    ) -> list[dict]:
        digests = [h for h in history if h.get("digest")]
        tried = max((parse_iso(h["ts"]) for h in digests), default=None)
        if tried and (now - tried).total_seconds() < interval_s:
            return []
        sent = [parse_iso(h["ts"]) for h in digests if h["event"] == "sent"]
        since = max(sent, default=None)
        groups: dict = {}  # dedupe_key -> [count, newest message]
        for h in history:
            if h["event"] == "queued" and not (
                since and parse_iso(h["ts"]) <= since
            ):
                group = groups.setdefault(h.get("dedupe_key"), [0, None])
                group[0] += 1
                group[1] = h["message"]
        lines = [
            f"{msg} (x{n})" if n > 1 else msg for n, msg in groups.values()
        ]
        if not lines:
            return []
        return [{**send(ctx, level, "\n".join(lines)), "digest": True}]

    notify.flush = flush
    return notify
