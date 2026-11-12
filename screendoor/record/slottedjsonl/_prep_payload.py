import contextlib

from ._extend import extend
from ._init import init
from ._trial_slots import resolve_slot, slots_path


def prep_payload(*, slot_bytes: int | None = None):
    """Give payload.slots.jsonl a slot for each of the ``n_trials`` trials.

    The daemon calls this before launching, so that every worker's slot
    exists before the worker starts. ``slot_bytes`` is the slot size in bytes,
    a multiple of 4096; it is fixed when the file is made, and read and
    write hooks left at ``slot_bytes=None`` take it from the file. None makes
    a new file with DEFAULT_SLOT (4096).
    """

    def prep_payload(ctx, n_trials: int) -> None:
        size = resolve_slot(slots_path(ctx), slot_bytes)
        with contextlib.suppress(FileExistsError):
            init(slots_path(ctx), 0, size)
        extend(slots_path(ctx), n_trials, size)

    return prep_payload
