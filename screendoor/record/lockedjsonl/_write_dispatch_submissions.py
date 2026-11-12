from __future__ import annotations

import os
import typing

from ._files import DISPATCH_SUBMISSIONS_FILE, append


def write_dispatch_submissions(
    *, timeout: float | None = None
) -> typing.Callable[[dict, dict], dict]:
    """Append one event to the dispatchdir's dispatch_submissions.jsonl, under
    an exclusive lock.

    Parameters
    ----------
    timeout : float or None, default None
        Seconds to wait for the lock before raising LockTimeoutError; None
        waits as long as it takes.

    Returns
    -------
    Callable[[dict, dict], dict]
        The ``how_write_dispatch_submissions`` hook: ``(ctx, record)``
        appends ``record`` and returns it as stamped.
    """

    def write_dispatch_submissions(ctx: dict, record: dict) -> dict:
        file = os.path.join(ctx["dispatchdir"], DISPATCH_SUBMISSIONS_FILE)
        return append(file, record, timeout)

    return write_dispatch_submissions
