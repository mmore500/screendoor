from ._files import path, read_events


def read_churn_memo(*, timeout: float | None = None):
    """Read every event in churn_memo.jsonl, under a shared lock."""

    def read_churn_memo(ctx) -> list:
        return read_events(path(ctx, "churn_memo"), timeout)

    return read_churn_memo
