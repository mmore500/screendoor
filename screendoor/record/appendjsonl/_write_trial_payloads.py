from __future__ import annotations

import typing

from ._files import append, path


def write_trial_payloads() -> typing.Callable[[dict, dict], dict]:
    """Append one event to trial_payloads.jsonl.

    Returns
    -------
    Callable[[dict, dict], dict]
        The ``how_write_trial_payloads`` hook: ``(ctx, record)`` appends
        ``record`` and returns it as stamped.
    """

    def write_trial_payloads(ctx: dict, record: dict) -> dict:
        return append(path(ctx, "trial_payloads"), record)

    return write_trial_payloads
