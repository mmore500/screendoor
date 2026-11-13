import typing

from ...auxlib._read_jsonl_tolerant import read_jsonl_tolerant
from ..appendjsonl._files import record_path
from ._read import read
from ._resolve_slot import file_slot, resolve_slot
from ._trial_slots import slots_path


def read_trial_payloads(
    *, slot_bytes: int | None = None
) -> typing.Callable[[dict], list[dict]]:
    """Create a `how_read_trial_payloads` hook that reads the run
    directory's `trial_payloads.jsonl` and the valid slots of its
    `trial_payloads.slots.jsonl`.

    Parameters
    ----------
    slot_bytes : int or None, default None
        The slot size; None takes the file's own, as `prep_trial_payloads`
        set it. A size that differs from the file's raises `ValueError`.

    Returns
    -------
    Callable[[dict], list[dict]]
        Hook `read_trial_payloads(ctx)`, returning the appended records
        followed by the slotted ones.
    """

    def read_trial_payloads(ctx: dict) -> list[dict]:
        events = read_jsonl_tolerant(record_path(ctx, "trial_payloads"))
        if file_slot(slots_path(ctx)) is not None:
            size = resolve_slot(slots_path(ctx), slot_bytes)
            events += read(slots_path(ctx), None, size).values()
        return events

    return read_trial_payloads
