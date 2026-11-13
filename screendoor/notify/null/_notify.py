import datetime
import typing


def notify() -> typing.Callable[..., list[dict]]:
    """Create a notifier that discards every notification.

    Returns
    -------
    Callable[..., list[dict]]
        Notifier `notify(ctx, level, message, data, history, now)`,
        returning no events.
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
