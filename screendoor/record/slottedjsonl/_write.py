import os
import time

from ._encode_slot import encode_slot
from ._resolve_slot import resolve_slot
from ._slot import SlotError, placeholder, pwrite_all


def write(
    path: str,
    i: int,
    record: dict,
    slot_bytes: int | None = None,
    wait: float = 120.0,
    clear_first: bool = False,
) -> None:
    """Write ``record`` into slot ``i``, replacing whatever it held.

    Waits up to ``wait`` seconds for the slot to exist, then raises
    SlotError: a writer never extends the file. With ``clear_first``, the
    slot is blanked and synced first, so that a crash while overwriting
    leaves padding, not a mix of two records.

    Parameters
    ----------
    path : str
        The slotted file.
    i : int
        The slot's index.
    record : dict
        The record to write.
    slot_bytes : int or None, default None
        The slot size; None takes the file's own.
    wait : float, default 120.0
        Seconds to wait for the slot to exist.
    clear_first : bool, default False
        Blank and sync the slot before writing it.

    Raises
    ------
    SlotError
        If the slot does not exist after ``wait`` seconds, ``record`` does
        not fit it, or a write is short.
    ValueError
        If ``i`` is negative.
    """
    slot_bytes = resolve_slot(path, slot_bytes)
    if i < 0:
        raise ValueError("index must be >= 0")
    buf = encode_slot(i, record, slot_bytes)
    deadline = time.monotonic() + wait
    while True:
        # no O_CREAT, no O_APPEND; reopened each time to see extensions
        try:
            fd = os.open(path, os.O_WRONLY)
        except FileNotFoundError:  # not made yet: wait, as for a short file
            fd = None
        if fd is not None and os.fstat(fd).st_size >= (i + 1) * slot_bytes:
            break
        if fd is not None:
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
