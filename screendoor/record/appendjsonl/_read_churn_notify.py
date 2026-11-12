from __future__ import annotations

import typing

from ...auxlib._read_jsonl_tolerant import read_jsonl_tolerant
from ._files import path


def read_churn_notify() -> typing.Callable[[dict], list[dict]]:
    """Read every event in churn_notify.jsonl.

    Returns
    -------
    Callable[[dict], list[dict]]
        The ``how_read_churn_notify`` hook: ``(ctx)`` returns the file's
        events.
    """

    def read_churn_notify(ctx: dict) -> list[dict]:
        return read_jsonl_tolerant(path(ctx, "churn_notify"))

    return read_churn_notify
