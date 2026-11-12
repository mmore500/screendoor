from ._files import append, path


def write_telemetry(*, timeout: float | None = None):
    """Append one event, with the dispatch's labels, to telemetry.jsonl, under
    an exclusive lock."""

    def write_telemetry(ctx, record: dict) -> dict:
        return append(
            path(ctx, "telemetry"), {**ctx.labels, **record}, timeout
        )

    return write_telemetry
