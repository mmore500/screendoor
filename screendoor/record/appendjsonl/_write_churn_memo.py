from __future__ import annotations

import typing

from ._files import append, path


def write_churn_memo() -> typing.Callable[[dict, dict], dict]:
    """Append one event to churn_memo.jsonl.

    Returns
    -------
    Callable[[dict, dict], dict]
        The ``how_write_churn_memo`` hook: ``(ctx, record)`` appends
        ``record`` and returns it as stamped.
    """

    def write_churn_memo(ctx: dict, record: dict) -> dict:
        return append(path(ctx, "churn_memo"), record)

    return write_churn_memo
