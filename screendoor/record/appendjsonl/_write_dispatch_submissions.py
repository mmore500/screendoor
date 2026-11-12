import os

from ._files import DISPATCH_SUBMISSIONS_FILE, append


def write_dispatch_submissions():
    """Append one event to a workdir's dispatch_submissions.jsonl."""

    def write_dispatch_submissions(workdir: str, record: dict) -> dict:
        return append(os.path.join(workdir, DISPATCH_SUBMISSIONS_FILE), record)

    return write_dispatch_submissions
