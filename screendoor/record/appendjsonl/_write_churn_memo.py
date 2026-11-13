import typing

from ._files import write_hook


def write_churn_memo(
    *, lock: bool = False, timeout: float | None = None
) -> typing.Callable[[dict, dict], dict]:
    """Create a `how_write_churn_memo` hook that appends to the run
    directory's `churn_memo.jsonl`.

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
        Hook `write_churn_memo(ctx, record)`, returning the record as
        stamped and written.
    """
    return write_hook("churn_memo", lock=lock, timeout=timeout)
