from ._files import append, path


def write_churn_notify(*, timeout: float | None = None):
    """Append one event to churn_notify.jsonl, under
    an exclusive lock."""

    def write_churn_notify(ctx, record: dict) -> dict:
        return append(path(ctx, "churn_notify"), record, timeout)

    return write_churn_notify
