import os

# a trial's payloads; the latest fills its slot
PAYLOAD_EVENTS = ("completed", "failed")


def slots_path(ctx) -> str:
    """The dispatch's slotted file: slot ``task_id`` belongs to that trial."""
    return os.path.join(ctx.run_dir, "trial_payloads.slots.jsonl")
