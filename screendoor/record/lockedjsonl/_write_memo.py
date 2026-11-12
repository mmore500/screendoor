from ._files import append, path


def write_memo(*, timeout: float | None = None):
    """Append one event, with the dispatch's labels, to memo.jsonl, under
    an exclusive lock."""

    def write_memo(ctx, record: dict) -> dict:
        return append(path(ctx, "memo"), {**ctx.labels, **record}, timeout)

    return write_memo
