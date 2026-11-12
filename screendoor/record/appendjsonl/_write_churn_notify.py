from ._files import append, path


def write_churn_notify():
    """Append one event to churn_notify.jsonl."""

    def write_churn_notify(ctx, record: dict) -> dict:
        return append(path(ctx, "churn_notify"), record)

    return write_churn_notify
