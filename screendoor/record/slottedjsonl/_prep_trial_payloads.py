from __future__ import annotations

import contextlib
import typing

from ._extend import extend
from ._init import init
from ._resolve_slot import resolve_slot
from ._trial_slots import slots_path


def prep_trial_payloads(
    *, slot_bytes: int | None = None
) -> typing.Callable[[dict, int], None]:
    """Give trial_payloads.slots.jsonl a slot for each of the ``n_trials``
    trials.

    The daemon calls this before launching, so that every worker's slot
    exists before the worker starts.

    Parameters
    ----------
    slot_bytes : int or None, default None
        The slot size in bytes, a multiple of 4096; it is fixed when the
        file is made, and read and write hooks left at ``slot_bytes=None``
        take it from the file. None makes a new file with DEFAULT_SLOT
        (32768).

    Returns
    -------
    Callable[[dict, int], None]
        The ``how_prep_trial_payloads`` hook: ``(ctx, n_trials)`` makes
        the file if missing and extends it to ``n_trials`` slots.
    """

    def prep_trial_payloads(ctx: dict, n_trials: int) -> None:
        size = resolve_slot(slots_path(ctx), slot_bytes)
        with contextlib.suppress(FileExistsError):
            init(slots_path(ctx), 0, size)
        extend(slots_path(ctx), n_trials, size)

    return prep_trial_payloads
