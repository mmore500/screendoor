from ._files import path, read_events


def read_churn_notify(*, timeout: float | None = None):
    """Read every event in churn_notify.jsonl, under a shared lock."""

    def read_churn_notify(ctx) -> list:
        return read_events(path(ctx, "churn_notify"), timeout)

    return read_churn_notify
