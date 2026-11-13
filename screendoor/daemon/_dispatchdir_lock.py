import contextlib
import fcntl
import os
import typing


@contextlib.contextmanager
def dispatchdir_lock(
    dispatchdir: str, *, wait: bool = False
) -> typing.Iterator[bool]:
    """Hold the dispatchdir's exclusive lock for the duration of the block,
    so that two local daemons never tick at once.

    Parameters
    ----------
    dispatchdir : str
        Path of the dispatchdir, created if missing.
    wait : bool, default False
        Whether to block until the lock is free, rather than yield False.

    Yields
    ------
    bool
        Whether the lock is held.
    """
    os.makedirs(dispatchdir, exist_ok=True)
    with open(os.path.join(dispatchdir, ".screendoor.lock"), "a") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
        except OSError:
            yield False
        else:
            yield True  # closing the file releases the lock
