import fcntl
import os

from ._resolve_slot import resolve_slot
from ._slot import placeholder, pwrite_all


def extend(path: str, n: int, slot_bytes: int | None = None) -> None:
    """Grow the file to ``n`` slots; never shrink it.

    Safe while writers fill existing slots, and repeatable: it rewrites a
    partial last slot left by a crashed extension. Extensions take turns
    under an exclusive lock on ``<path>.extend.lock``.

    Parameters
    ----------
    path : str
        The slotted file.
    n : int
        How many slots it should have.
    slot_bytes : int or None, default None
        The slot size; None takes the file's own.
    """
    slot_bytes = resolve_slot(path, slot_bytes)
    with open(path + ".extend.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        fd = os.open(path, os.O_RDWR)
        try:
            complete = os.fstat(fd).st_size // slot_bytes
            for i in range(complete, n):
                pwrite_all(fd, placeholder(slot_bytes), i * slot_bytes)
            os.fsync(fd)
        finally:
            os.close(fd)
