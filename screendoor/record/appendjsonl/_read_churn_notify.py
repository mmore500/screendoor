from ...auxlib._read_jsonl_tolerant import read_jsonl_tolerant
from ._files import path


def read_churn_notify():
    """Read every event in churn_notify.jsonl."""

    def read_churn_notify(ctx) -> list:
        return read_jsonl_tolerant(path(ctx, "churn_notify"))

    return read_churn_notify
