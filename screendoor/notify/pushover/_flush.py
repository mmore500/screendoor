import datetime
import typing

from ._send import send


def flush() -> typing.Callable[
    [dict, str, list[dict], datetime.datetime], list[dict]
]:
    """Create a flush that retries the latest failed sends.

    Returns
    -------
    Callable[[dict, str, list[dict], datetime.datetime], list[dict]]
        Flush `flush(ctx, level, history, now)`, which resends the latest
        three messages in `history` whose sends failed and were not since
        sent, and returns their events.
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
