from ...auxlib._fold_trial_events import fold_trial_events
from ...auxlib._read_jsonl_tolerant import read_jsonl_tolerant
from ..jsonl._files import path
from ._read import read
from ._trial_slots import file_slot, resolve_slot, slots_path


def read_payload(*, slot_bytes: int | None = None):
    """Read one dict per trial from payload.jsonl and the valid slots of
    payload.slots.jsonl; with ``raw``, the unfolded events.

    ``slot_bytes`` (bytes) defaults to the file's own, as set by
    prep_payload(); a different size raises.
    """

    def read_payload(ctx, *, raw: bool = False) -> list:
        events = read_jsonl_tolerant(path(ctx, "payload"))
        if file_slot(slots_path(ctx)) is not None:
            size = resolve_slot(slots_path(ctx), slot_bytes)
            events += read(slots_path(ctx), None, size).values()
        return events if raw else fold_trial_events(events)

    return read_payload
