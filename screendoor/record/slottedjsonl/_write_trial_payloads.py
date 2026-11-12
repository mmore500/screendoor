from __future__ import annotations

import logging
import os
import typing

from ...auxlib._append_jsonl_line import stamp
from ..appendjsonl._files import append, path
from ._decode_slot import decode_slot
from ._resolve_slot import resolve_slot
from ._slot import SlotError
from ._trial_slots import PAYLOAD_EVENTS, slots_path
from ._write import write


def _holds_completed(file: str, i: int, slot_bytes: int) -> bool:
    try:
        with open(file, "rb") as fh:
            record = decode_slot(
                i, os.pread(fh.fileno(), slot_bytes, i * slot_bytes)
            )
    except OSError:
        return False
    return bool(record) and record.get("event") == "completed"


def write_trial_payloads(
    *, slot_bytes: int | None = None, timeout: float = 120.0
) -> typing.Callable[[dict, dict], dict]:
    """Write each trial's payload into slot ``task_id`` of
    trial_payloads.slots.jsonl, lock-free.

    A later payload replaces an earlier one, except that a ``failed``
    never replaces a ``completed`` (as when folding appended payloads). A
    payload too large for its slot is appended to trial_payloads.jsonl
    instead.

    Parameters
    ----------
    slot_bytes : int or None, default None
        The slot size, as for resolve_slot.
    timeout : float, default 120.0
        Seconds to wait for the slot to exist.

    Returns
    -------
    Callable[[dict, dict], dict]
        The ``how_write_trial_payloads`` hook: ``(ctx, record)`` writes
        ``record`` and returns it as stamped.
    """

    def write_trial_payloads(ctx: dict, record: dict) -> dict:
        task_id = record.get("task_id")
        if record["event"] in PAYLOAD_EVENTS and task_id is not None:
            stamped = stamp(record)
            file = slots_path(ctx)
            try:
                size = resolve_slot(file, slot_bytes)
                if record["event"] == "failed" and _holds_completed(
                    file, task_id, size
                ):
                    return stamped  # the trial already succeeded
                write(file, task_id, stamped, size, timeout)
                return stamped
            except SlotError as e:
                logging.warning(
                    "screendoor: trial %s goes to trial_payloads.jsonl: %s",
                    record["trial_uuid"],
                    e,
                )
        return append(path(ctx, "trial_payloads"), record)

    return write_trial_payloads
