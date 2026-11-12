from ._files import path, read_events


def read_trial_submissions(*, timeout: float | None = None):
    """Read every event in trial_submissions.jsonl, under a shared lock."""

    def read_trial_submissions(ctx) -> list:
        return read_events(path(ctx, "trial_submissions"), timeout)

    return read_trial_submissions
