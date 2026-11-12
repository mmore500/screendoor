import os
import time

from ._encode_slot import encode_slot
from ._slot import DEFAULT_SLOT, SlotError, check_slot, placeholder, pwrite_all


def write(
    path: str,
    i: int,
    record: dict,
    slot_bytes: int = DEFAULT_SLOT,
    wait: float = 120.0,
    clear_first: bool = False,
) -> None:
    """Write ``record`` into slot ``i``, replacing whatever it held.

    Waits up to ``wait`` seconds for the slot to exist, then raises
    SlotError: a writer never extends the file. With ``clear_first``, the
    slot is blanked and synced first, so that a crash while overwriting
    leaves padding, not a mix of two records.
    """
    check_slot(slot_bytes)
    if i < 0:
        raise ValueError("index must be >= 0")
    buf = encode_slot(i, record, slot_bytes)
    deadline = time.monotonic() + wait
    while True:
        # no O_CREAT, no O_APPEND; reopened each time to see extensions
        fd = os.open(path, os.O_WRONLY)
        if os.fstat(fd).st_size >= (i + 1) * slot_bytes:
            break
        os.close(fd)
        if time.monotonic() >= deadline:
            raise SlotError(
                f"slot {i} does not exist after {wait}s; run extend()"
            )
        time.sleep(min(2.0, wait))
    try:
        if clear_first:
            pwrite_all(fd, placeholder(slot_bytes), i * slot_bytes)
            os.fsync(fd)
        pwrite_all(fd, buf, i * slot_bytes)
        os.fsync(fd)
    finally:
        os.close(fd)
