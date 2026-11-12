from __future__ import annotations

import typing

from ...auxlib._read_jsonl_tolerant import read_jsonl_tolerant
from ._files import path


def read_trial_payloads() -> typing.Callable[[dict], list[dict]]:
    """Read every event in trial_payloads.jsonl.

    Returns
    -------
    Callable[[dict], list[dict]]
        The ``how_read_trial_payloads`` hook: ``(ctx)`` returns the file's
        events.
    """

    def read_trial_payloads(ctx: dict) -> list[dict]:
        return read_jsonl_tolerant(path(ctx, "trial_payloads"))

    return read_trial_payloads
