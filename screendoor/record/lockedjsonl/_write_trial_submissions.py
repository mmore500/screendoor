from ._files import append, path


def write_trial_submissions(*, timeout: float | None = None):
    """Append one event, with the dispatch's labels, to trial_submissions.jsonl,
    under an exclusive lock."""

    def write_trial_submissions(ctx, record: dict) -> dict:
        record = {**ctx.labels, **record}
        return append(path(ctx, "trial_submissions"), record, timeout)

    return write_trial_submissions
