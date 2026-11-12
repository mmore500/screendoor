from __future__ import annotations

import os
import typing

from ._files import DISPATCH_PAYLOADS_FILE, append


def write_dispatch_payloads() -> typing.Callable[[dict, dict], dict]:
    """Append one event to the dispatchdir's dispatch_payloads.jsonl.

    Returns
    -------
    Callable[[dict, dict], dict]
        The ``how_write_dispatch_payloads`` hook: ``(ctx, record)``
        appends ``record`` and returns it as stamped.
    """

    def write_dispatch_payloads(ctx: dict, record: dict) -> dict:
        return append(
            os.path.join(ctx["dispatchdir"], DISPATCH_PAYLOADS_FILE), record
        )

    return write_dispatch_payloads
