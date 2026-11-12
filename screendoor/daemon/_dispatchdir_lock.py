import contextlib
import fcntl
import os


@contextlib.contextmanager
def dispatchdir_lock(dispatchdir: str, *, wait: bool = False):
    """Yield whether this process got the dispatchdir's exclusive lock.

    Keeps two local daemons from ticking at once. With ``wait``, block
    until the lock is free.
    """
    os.makedirs(dispatchdir, exist_ok=True)
    with open(os.path.join(dispatchdir, ".screendoor.lock"), "a") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
        except OSError:
            yield False
        else:
            yield True  # closing the file releases the lock
