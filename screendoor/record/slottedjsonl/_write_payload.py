import logging

from ...auxlib._append_jsonl_line import SCHEMA
from ...auxlib._now_iso import now_iso
from ..jsonl._files import append, path
from ._slot import SlotError
from ._trial_slots import WORKER_EVENTS, resolve_slot, slots_path
from ._write import write


def write_payload(*, slot_bytes: int | None = None, wait: float = 120.0):
    """Write what workers record into the trial's own slot, lock-free.

    A worker's ``started``, ``completed`` and ``failed`` events go to slot
    ``task_id`` of payload.slots.jsonl, each replacing the last. Everything
    else, which only the daemon writes, is appended to payload.jsonl; so is
    an event too large for its slot. ``slot_bytes`` (bytes) defaults to the
    file's own, as set by prep_payload(); a different size raises.
    """

    def write_payload(ctx, record: dict) -> dict:
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
                    "screendoor: trial %s goes to payload.jsonl: %s",
                    record["trial_uuid"],
                    e,
                )
        return append(path(ctx, "payload"), record)

    return write_payload
