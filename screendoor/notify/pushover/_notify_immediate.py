from __future__ import annotations

import typing

from ._flush import flush
from ._send import send

if typing.TYPE_CHECKING:
    import datetime


def notify_immediate() -> typing.Callable[..., list[dict]]:
    """Send every notification right away.

    Returns
    -------
    Callable[..., list]
        The notifier: ``(ctx, level, message, data, history, now)`` sends
        ``message`` and returns its event. Its ``flush`` retries failed
        sends.
    """

    def notify(
        ctx: dict,
        level: str,
        message: str,
        data: dict,
        history: list[dict],
        now: datetime.datetime,
    ) -> list[dict]:
        return [send(ctx, level, message)]

    notify.flush = flush()
    return notify
