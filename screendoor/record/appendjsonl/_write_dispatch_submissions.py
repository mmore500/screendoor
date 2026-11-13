import typing

from ._files import write_hook


def write_dispatch_submissions(
    *, lock: bool = False, timeout: float | None = None
) -> typing.Callable[[dict, dict], dict]:
    """Create a `how_write_dispatch_submissions` hook that appends to the
    dispatchdir's `dispatch_submissions.jsonl`.

    Parameters
    ----------
    lock : bool, default False
        Whether to write under an exclusive fcntl lock, for filesystems
        where `O_APPEND` writes can tear (NFS across nodes).
    timeout : float or None, default None
        Seconds to wait for the lock before raising `LockTimeoutError`;
        None waits as long as it takes.

    Returns
    -------
    Callable[[dict, dict], dict]
        Hook `write_dispatch_submissions(ctx, record)`, returning the
        record as stamped and written.
    """
    return write_hook("dispatch_submissions", lock=lock, timeout=timeout)
