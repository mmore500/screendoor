import logging

from ...auxlib._append_jsonl_line import SCHEMA
from ...auxlib._now_iso import now_iso
from ..appendjsonl._files import append, path
from ._slot import SlotError
from ._trial_slots import WORKER_EVENTS, resolve_slot, slots_path
from ._write import write


def write_trial_payloads(
    *, slot_bytes: int | None = None, wait: float = 120.0
):
    """Write each trial's payload into its own slot, lock-free.

    A ``completed`` or ``failed`` payload with a ``task_id`` goes to slot
    ``task_id`` of trial_payloads.slots.jsonl, replacing any earlier one.
    Others (the daemon's ``failed: lost``, which has no task_id) are
    appended to trial_payloads.jsonl; so is a payload too large for its
    slot. ``slot_bytes`` defaults to the file's own, as set by
    prep_trial_payloads(); a different size raises.
    """

    def write_trial_payloads(ctx, record: dict) -> dict:
        record = {**ctx.labels, **record}
        task_id = record.get("task_id")
        if record["event"] in WORKER_EVENTS and task_id is not None:
            stamped = {"schema": SCHEMA, "ts": now_iso(), **record}
            try:
                size = resolve_slot(slots_path(ctx), slot_bytes)
                write(slots_path(ctx), task_id, stamped, size, wait)
                return stamped
            except SlotError as e:
                logging.warning(
                    "screendoor: trial %s goes to trial_payloads.jsonl: %s",
                    record["trial_uuid"],
                    e,
                )
        return append(path(ctx, "trial_payloads"), record)

    return write_trial_payloads
