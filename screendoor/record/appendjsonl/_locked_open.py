import contextlib
import fcntl
import os
import threading
import time
import typing

POLL_S = 0.05


class LockTimeoutError(TimeoutError):
    """Raised when a file's lock is not acquired within the timeout."""


# fcntl locks belong to the process, not the thread or the descriptor, so
# threads of one process (a worker's stdout and stderr pumps) would all hold
# the same lock at once; a per-path thread lock excludes them too
_thread_locks: dict = {}
_guard = threading.Lock()


def _thread_lock(path: str) -> threading.Lock:
    with _guard:
        return _thread_locks.setdefault(
            os.path.realpath(path), threading.Lock()
        )


def _remaining(deadline: float | None) -> float:
    return -1 if deadline is None else max(0.0, deadline - time.monotonic())


@contextlib.contextmanager
def locked_open(
    path: str, flags: int, *, exclusive: bool, timeout: float | None = None
) -> typing.Iterator[int]:
    """Open `path` and yield its descriptor under an fcntl record lock.

    The lock is exclusive for writers and shared for readers. On exit, the
    lock is released and the descriptor closed.

    POSIX locks are dropped when the process closes *any* descriptor of the
    file, so nothing else in the process should open a locked file while
    the lock is held; the per-path thread lock covers this package's own
    calls.

    Parameters
    ----------
    path : str
        The file to open.
    flags : int
        Flags for `os.open`; a file it creates gets mode 600.
    exclusive : bool
        Whether to lock exclusively, to write, rather than shared, to read.
    timeout : float or None, default None
        Seconds to wait for the lock before raising `LockTimeoutError`;
        None waits as long as it takes.

    Yields
    ------
    int
        The locked file descriptor.

    Raises
    ------
    LockTimeoutError
        If the lock is not acquired within `timeout` seconds.
    """
    deadline = None if timeout is None else time.monotonic() + timeout
    tlock = _thread_lock(path)
    if not tlock.acquire(timeout=_remaining(deadline)):
        raise LockTimeoutError(f"{path}: lock held in this process")
    try:
        fd = os.open(path, flags, 0o600)
        try:
            kind = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
            if deadline is None:
                fcntl.lockf(fd, kind)
            else:
                while True:
                    try:
                        fcntl.lockf(fd, kind | fcntl.LOCK_NB)
                        break
                    except OSError:  # EACCES or EAGAIN: held elsewhere
                        if time.monotonic() >= deadline:
                            raise LockTimeoutError(
                                f"{path}: lock not acquired in {timeout}s"
                            ) from None
                        time.sleep(min(POLL_S, _remaining(deadline)))
            try:
                yield fd
            finally:
                fcntl.lockf(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)
    finally:
        tlock.release()
