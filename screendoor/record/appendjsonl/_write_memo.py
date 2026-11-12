from ._files import append, path


def write_memo():
    """Append one event, with the dispatch's labels, to memo.jsonl."""

    def write_memo(ctx, record: dict) -> dict:
        return append(path(ctx, "memo"), {**ctx.labels, **record})

    return write_memo
