from __future__ import annotations

import typing

from ._send import send

if typing.TYPE_CHECKING:
    import datetime


def flush() -> typing.Callable[
    [dict, str, list[dict], datetime.datetime],
    list[dict],
]:
    """Retry up to three messages whose sends failed.

    Returns
    -------
    Callable[[dict, str, list, datetime], list]
        The flush: ``(ctx, level, history, now)`` resends the latest three
        failed messages in ``history`` not since sent, and returns their
        events.
    """

    def flush(
        ctx: dict,
        level: str,
        history: list[dict],
        now: datetime.datetime,
    ) -> list[dict]:
        sent = {h.get("message") for h in history if h["event"] == "sent"}
        failed = dict.fromkeys(
            h["message"]
            for h in history
            if h["event"] == "send_failed" and h["message"] not in sent
        )
        return [send(ctx, level, message) for message in list(failed)[-3:]]

    return flush
