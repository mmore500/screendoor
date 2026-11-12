import os

from ._files import DISPATCH_SUBMISSIONS_FILE, append


def write_dispatch_submissions():
    """Append one event to the dispatchdir's dispatch_submissions.jsonl."""

    def write_dispatch_submissions(ddhooks, record: dict) -> dict:
        return append(
            os.path.join(ddhooks.dispatchdir, DISPATCH_SUBMISSIONS_FILE),
            record,
        )

    return write_dispatch_submissions
