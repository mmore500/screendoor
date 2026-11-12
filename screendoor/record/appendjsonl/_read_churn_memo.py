from __future__ import annotations

import typing

from ...auxlib._read_jsonl_tolerant import read_jsonl_tolerant
from ._files import path


def read_churn_memo() -> typing.Callable[[dict], list[dict]]:
    """Read every event in churn_memo.jsonl.

    Returns
    -------
    Callable[[dict], list[dict]]
        The ``how_read_churn_memo`` hook: ``(ctx)`` returns the file's
        events.
    """

    def read_churn_memo(ctx: dict) -> list[dict]:
        return read_jsonl_tolerant(path(ctx, "churn_memo"))

    return read_churn_memo
