from __future__ import annotations

import typing

from ...auxlib._read_jsonl_tolerant import read_jsonl_tolerant
from ..appendjsonl._files import path
from ._read import read
from ._resolve_slot import file_slot, resolve_slot
from ._trial_slots import slots_path


def read_trial_payloads(
    *, slot_bytes: int | None = None
) -> typing.Callable[[dict], list[dict]]:
    """Read every event in trial_payloads.jsonl and the valid slots of
    trial_payloads.slots.jsonl.

    Parameters
    ----------
    slot_bytes : int or None, default None
        The slot size; None takes the file's own, as set by
        prep_trial_payloads(), and a different size raises.

    Returns
    -------
    Callable[[dict], list[dict]]
        The ``how_read_trial_payloads`` hook: ``(ctx)`` returns the
        appended events, then the slotted ones.
    """

    def read_trial_payloads(ctx: dict) -> list[dict]:
        events = read_jsonl_tolerant(path(ctx, "trial_payloads"))
        if file_slot(slots_path(ctx)) is not None:
            size = resolve_slot(slots_path(ctx), slot_bytes)
            events += read(slots_path(ctx), None, size).values()
        return events

    return read_trial_payloads
