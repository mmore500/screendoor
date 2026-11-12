from ._files import append, path


def write_churn_memo():
    """Append one event to churn_memo.jsonl."""

    def write_churn_memo(ctx, record: dict) -> dict:
        return append(path(ctx, "churn_memo"), record)

    return write_churn_memo
