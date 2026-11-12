from __future__ import annotations

import typing

from ._files import path, read_events


def read_trial_telemetry(
    *, timeout: float | None = None
) -> typing.Callable[[dict], list[dict]]:
    """Read every event in trial_telemetry.jsonl, under a shared lock.

    Parameters
    ----------
    timeout : float or None, default None
        Seconds to wait for the lock before raising LockTimeoutError; None
        waits as long as it takes.

    Returns
    -------
    Callable[[dict], list[dict]]
        The ``how_read_trial_telemetry`` hook: ``(ctx)`` returns the file's
        events.
    """

    def read_trial_telemetry(ctx: dict) -> list[dict]:
        return read_events(path(ctx, "trial_telemetry"), timeout)

    return read_trial_telemetry
