from ._files import path, read_events


def read_notify(*, timeout: float | None = None):
    """Read every event in notify.jsonl, under a shared lock."""

    def read_notify(ctx) -> list:
        return read_events(path(ctx, "notify"), timeout)

    return read_notify
