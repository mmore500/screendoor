from ._files import append, path


def write_notify():
    """Append one event, with the dispatch's labels, to notify.jsonl."""

    def write_notify(ctx, record: dict) -> dict:
        return append(path(ctx, "notify"), {**ctx.labels, **record})

    return write_notify
