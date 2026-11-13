import os

# the trial payload events; the latest fills the trial's slot
PAYLOAD_EVENTS = ("completed", "failed")


def slots_path(ctx: dict) -> str:
    """Return the path of the dispatch's slotted file,
    `trial_payloads.slots.jsonl`, in which slot `task_id` belongs to that
    trial.

    Parameters
    ----------
    ctx : dict
        The hook context.

    Returns
    -------
    str
        The file's path.
    """
    return os.path.join(ctx["run_dir"], "trial_payloads.slots.jsonl")
