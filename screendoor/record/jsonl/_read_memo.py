from ...auxlib._read_jsonl_tolerant import read_jsonl_tolerant
from ._files import path


def read_memo():
    """Read memo payloads, oldest first; with ``raw``, the whole events."""

    def read_memo(ctx, *, raw: bool = False) -> list:
        by_index: dict = {}  # a crash can leave a step's memo written twice
        events = read_jsonl_tolerant(path(ctx, "memo"))
        for e in sorted(events, key=lambda e: (e["index"], e["ts"])):
            by_index.setdefault(e["index"], e)
        return [e if raw else e["data"] for e in by_index.values()]

    return read_memo
