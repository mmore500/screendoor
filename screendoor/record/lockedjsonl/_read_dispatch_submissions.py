import os

from ._files import DISPATCH_SUBMISSIONS_FILE, read_events


def read_dispatch_submissions(*, timeout: float | None = None):
    """Read every event in a workdir's dispatch_submissions.jsonl, under a
    shared lock."""

    def read_dispatch_submissions(workdir: str) -> list:
        file = os.path.join(workdir, DISPATCH_SUBMISSIONS_FILE)
        return read_events(file, timeout)

    return read_dispatch_submissions
