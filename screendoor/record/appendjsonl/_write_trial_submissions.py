from ._files import append, path


def write_trial_submissions():
    """Append one event, with the dispatch's labels, to trial_submissions.jsonl."""

    def write_trial_submissions(ctx, record: dict) -> dict:
        return append(path(ctx, "trial_submissions"), {**ctx.labels, **record})

    return write_trial_submissions
