from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    import datetime


def notify() -> typing.Callable[..., list[dict]]:
    """Do nothing.

    Returns
    -------
    Callable[..., list]
        The notifier: ``(ctx, level, message, data, history, now)``
        returns no events.
    """

    def notify(
        ctx: dict,
        level: str,
        message: str,
        data: dict,
        history: list[dict],
        now: datetime.datetime,
    ) -> list[dict]:
        return []

    return notify
