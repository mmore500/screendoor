import os

from ...auxlib._read_jsonl_tolerant import read_jsonl_tolerant
from ._files import DISPATCH_SUBMISSIONS_FILE


def read_dispatch_submissions():
    """Read every event in the dispatchdir's dispatch_submissions.jsonl."""

    def read_dispatch_submissions(ddhooks) -> list:
        return read_jsonl_tolerant(
            os.path.join(ddhooks.dispatchdir, DISPATCH_SUBMISSIONS_FILE)
        )

    return read_dispatch_submissions
