import os

from ._slot import DEFAULT_SLOT, check_slot

# a trial's payloads; the latest fills its slot
WORKER_EVENTS = ("completed", "failed")


def slots_path(ctx) -> str:
    """The dispatch's slotted file: slot ``task_id`` belongs to that trial."""
    return os.path.join(ctx.run_dir, "trial_payloads.slots.jsonl")


def file_slot(path: str) -> int | None:
    """The slot size a slotted file was made with: its first line's length.

    None if the file is missing or has no complete first slot yet.
    """
    try:
        with open(path, "rb") as fh:
            head = b""
            while b"\n" not in head:
                chunk = fh.read(4096)
                if not chunk:
                    return None
                head += chunk
    except FileNotFoundError:
        return None
    return head.index(b"\n") + 1


def resolve_slot(path: str, slot_bytes: int | None) -> int:
    """The slot size to use for ``path``.

    ``None`` takes the file's own, or DEFAULT_SLOT for a file not yet
    made. A size given that differs from the file's raises ValueError.
    """
    found = file_slot(path)
    if slot_bytes is None:
        return found or DEFAULT_SLOT
    check_slot(slot_bytes)
    if found is not None and found != slot_bytes:
        raise ValueError(f"{path} has {found}-byte slots, not {slot_bytes}")
    return slot_bytes
