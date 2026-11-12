from __future__ import annotations

import os

# a trial's payloads; the latest fills its slot
PAYLOAD_EVENTS = ("completed", "failed")


def slots_path(ctx: dict) -> str:
    """The dispatch's slotted file: slot ``task_id`` belongs to that trial.

    Parameters
    ----------
    ctx : dict
        The dispatch.

    Returns
    -------
    str
        The path of its trial_payloads.slots.jsonl.
    """
    return os.path.join(ctx["run_dir"], "trial_payloads.slots.jsonl")
