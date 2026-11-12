from __future__ import annotations

import typing

from ...auxlib._read_jsonl_tolerant import read_jsonl_tolerant
from ._files import path


def read_trial_telemetry() -> typing.Callable[[dict], list[dict]]:
    """Read every event in trial_telemetry.jsonl.

    Returns
    -------
    Callable[[dict], list[dict]]
        The ``how_read_trial_telemetry`` hook: ``(ctx)`` returns the file's
        events.
    """

    def read_trial_telemetry(ctx: dict) -> list[dict]:
        return read_jsonl_tolerant(path(ctx, "trial_telemetry"))

    return read_trial_telemetry
