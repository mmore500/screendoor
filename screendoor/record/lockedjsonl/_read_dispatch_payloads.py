from __future__ import annotations

import os
import typing

from ._files import DISPATCH_PAYLOADS_FILE, read_events


def read_dispatch_payloads(
    *, timeout: float | None = None
) -> typing.Callable[[dict], list[dict]]:
    """Read every event in the dispatchdir's dispatch_payloads.jsonl, under a
    shared lock.

    Parameters
    ----------
    timeout : float or None, default None
        Seconds to wait for the lock before raising LockTimeoutError; None
        waits as long as it takes.

    Returns
    -------
    Callable[[dict], list[dict]]
        The ``how_read_dispatch_payloads`` hook: ``(ctx)`` returns the
        file's events.
    """

    def read_dispatch_payloads(ctx: dict) -> list[dict]:
        file = os.path.join(ctx["dispatchdir"], DISPATCH_PAYLOADS_FILE)
        return read_events(file, timeout)

    return read_dispatch_payloads
