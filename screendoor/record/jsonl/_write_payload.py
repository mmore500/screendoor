from ._files import append, path


def write_payload():
    """Append one event, with the dispatch's labels, to payload.jsonl."""

    def write_payload(ctx, record: dict) -> dict:
        return append(path(ctx, "payload"), {**ctx.labels, **record})

    return write_payload
