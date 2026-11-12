from ._files import append, path


def write_notify(*, timeout: float | None = None):
    """Append one event, with the dispatch's labels, to notify.jsonl, under
    an exclusive lock."""

    def write_notify(ctx, record: dict) -> dict:
        return append(path(ctx, "notify"), {**ctx.labels, **record}, timeout)

    return write_notify
