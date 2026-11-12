from ._files import path, read_events


def read_memo(*, timeout: float | None = None):
    """Read memo payloads, oldest first, under a shared lock; with
    ``raw``, the whole events."""

    def read_memo(ctx, *, raw: bool = False) -> list:
        by_index: dict = {}  # a crash can leave a step's memo written twice
        events = read_events(path(ctx, "memo"), timeout)
        for e in sorted(events, key=lambda e: (e["index"], e["ts"])):
            by_index.setdefault(e["index"], e)
        return [e if raw else e["data"] for e in by_index.values()]

    return read_memo
