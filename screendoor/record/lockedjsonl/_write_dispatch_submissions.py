import os

from ._files import DISPATCH_SUBMISSIONS_FILE, append


def write_dispatch_submissions(*, timeout: float | None = None):
    """Append one event to the dispatchdir's dispatch_submissions.jsonl, under an
    exclusive lock."""

    def write_dispatch_submissions(ddhooks, record: dict) -> dict:
        file = os.path.join(ddhooks.dispatchdir, DISPATCH_SUBMISSIONS_FILE)
        return append(file, record, timeout)

    return write_dispatch_submissions
