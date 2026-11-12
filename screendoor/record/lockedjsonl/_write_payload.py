from ._files import append, path


def write_payload(*, timeout: float | None = None):
    """Append one event, with the dispatch's labels, to payload.jsonl, under
    an exclusive lock."""

    def write_payload(ctx, record: dict) -> dict:
        return append(path(ctx, "payload"), {**ctx.labels, **record}, timeout)

    return write_payload
