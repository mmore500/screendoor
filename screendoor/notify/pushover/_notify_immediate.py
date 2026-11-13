import datetime
import typing

from ._flush import flush
from ._send import send


def notify_immediate() -> typing.Callable[..., list[dict]]:
    """Create a notifier that sends every notification right away.

    Returns
    -------
    Callable[..., list[dict]]
        Notifier `notify(ctx, level, message, data, history, now)`,
        returning the send's event. Its `flush` retries failed sends.
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
