from ...auxlib._read_jsonl_tolerant import read_jsonl_tolerant
from ..appendjsonl._files import path
from ._read import read
from ._resolve_slot import file_slot, resolve_slot
from ._trial_slots import slots_path


def read_trial_payloads(*, slot_bytes: int | None = None):
    """Read every event in trial_payloads.jsonl and the valid slots of
    trial_payloads.slots.jsonl.

    ``slot_bytes`` defaults to the file's own, as set by
    prep_trial_payloads(); a different size raises.
    """

    def read_trial_payloads(ctx) -> list:
        events = read_jsonl_tolerant(path(ctx, "trial_payloads"))
        if file_slot(slots_path(ctx)) is not None:
            size = resolve_slot(slots_path(ctx), slot_bytes)
            events += read(slots_path(ctx), None, size).values()
        return events

    return read_trial_payloads
