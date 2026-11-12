from ._files import append, path


def write_telemetry():
    """Append one event, with the dispatch's labels, to telemetry.jsonl."""

    def write_telemetry(ctx, record: dict) -> dict:
        return append(path(ctx, "telemetry"), {**ctx.labels, **record})

    return write_telemetry
