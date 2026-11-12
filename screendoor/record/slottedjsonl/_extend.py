import fcntl
import os

from ._slot import DEFAULT_SLOT, check_slot, placeholder


def extend(path: str, n_new: int, slot_bytes: int = DEFAULT_SLOT) -> None:
    """Grow the file to ``n_new`` slots; never shrink it.

    Safe while writers fill existing slots, and repeatable: it rewrites a
    partial last slot left by a crashed extension. Extensions take turns
    under an exclusive lock on ``<path>.extend.lock``.
    """
    check_slot(slot_bytes)
    with open(path + ".extend.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        fd = os.open(path, os.O_RDWR)
        try:
            complete = os.fstat(fd).st_size // slot_bytes
            for i in range(complete, n_new):
                os.pwrite(fd, placeholder(slot_bytes), i * slot_bytes)
            os.fsync(fd)
        finally:
            os.close(fd)
