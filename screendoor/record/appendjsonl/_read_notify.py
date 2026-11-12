from ...auxlib._read_jsonl_tolerant import read_jsonl_tolerant
from ._files import path


def read_notify():
    """Read every event in notify.jsonl."""

    def read_notify(ctx) -> list:
        return read_jsonl_tolerant(path(ctx, "notify"))

    return read_notify
