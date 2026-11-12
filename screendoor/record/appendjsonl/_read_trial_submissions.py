from ...auxlib._read_jsonl_tolerant import read_jsonl_tolerant
from ._files import path


def read_trial_submissions():
    """Read every event in trial_submissions.jsonl."""

    def read_trial_submissions(ctx) -> list:
        return read_jsonl_tolerant(path(ctx, "trial_submissions"))

    return read_trial_submissions
