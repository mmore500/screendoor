import os

from ._files import DISPATCH_SUBMISSIONS_FILE, read_events


def read_dispatch_submissions(*, timeout: float | None = None):
    """Read every event in the dispatchdir's dispatch_submissions.jsonl, under a
    shared lock."""

    def read_dispatch_submissions(ddhooks) -> list:
        file = os.path.join(ddhooks.dispatchdir, DISPATCH_SUBMISSIONS_FILE)
        return read_events(file, timeout)

    return read_dispatch_submissions
