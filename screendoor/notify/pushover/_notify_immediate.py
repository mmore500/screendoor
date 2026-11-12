from ._flush import flush
from ._send import send


def notify_immediate():
    """Send every notification right away."""

    def notify(ctx, level, message, data, history, now) -> list:
        return [send(ctx, level, message)]

    notify.flush = flush()
    return notify
