from __future__ import annotations

import typing

from ._files import append, path


def write_churn_notify(
    *, timeout: float | None = None
) -> typing.Callable[[dict, dict], dict]:
    """Append one event to churn_notify.jsonl, under an exclusive lock.

    Parameters
    ----------
    timeout : float or None, default None
        Seconds to wait for the lock before raising LockTimeoutError; None
        waits as long as it takes.

    Returns
    -------
    Callable[[dict, dict], dict]
        The ``how_write_churn_notify`` hook: ``(ctx, record)`` appends
        ``record`` and returns it as stamped.
    """

    def write_churn_notify(ctx: dict, record: dict) -> dict:
        return append(path(ctx, "churn_notify"), record, timeout)

    return write_churn_notify
