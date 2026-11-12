from ...auxlib._read_jsonl_tolerant import read_jsonl_tolerant
from ._files import path


def read_churn_memo():
    """Read every event in churn_memo.jsonl."""

    def read_churn_memo(ctx) -> list:
        return read_jsonl_tolerant(path(ctx, "churn_memo"))

    return read_churn_memo
