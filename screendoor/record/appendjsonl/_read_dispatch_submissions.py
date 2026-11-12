from __future__ import annotations

import os
import typing

from ...auxlib._read_jsonl_tolerant import read_jsonl_tolerant
from ._files import DISPATCH_SUBMISSIONS_FILE


def read_dispatch_submissions() -> typing.Callable[[dict], list[dict]]:
    """Read every event in the dispatchdir's dispatch_submissions.jsonl.

    Returns
    -------
    Callable[[dict], list[dict]]
        The ``how_read_dispatch_submissions`` hook: ``(ctx)`` returns the
        file's events.
    """

    def read_dispatch_submissions(ctx: dict) -> list[dict]:
        return read_jsonl_tolerant(
            os.path.join(ctx["dispatchdir"], DISPATCH_SUBMISSIONS_FILE)
        )

    return read_dispatch_submissions
