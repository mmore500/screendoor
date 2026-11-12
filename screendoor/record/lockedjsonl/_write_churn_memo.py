from ._files import append, path


def write_churn_memo(*, timeout: float | None = None):
    """Append one event to churn_memo.jsonl, under
    an exclusive lock."""

    def write_churn_memo(ctx, record: dict) -> dict:
        return append(path(ctx, "churn_memo"), record, timeout)

    return write_churn_memo
