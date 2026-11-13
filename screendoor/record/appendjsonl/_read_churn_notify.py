import typing

from ._files import read_hook


def read_churn_notify(
    *, lock: bool = False, timeout: float | None = None
) -> typing.Callable[[dict], list[dict]]:
    """Create a `how_read_churn_notify` hook that reads the run directory's
    `churn_notify.jsonl`.

    Parameters
    ----------
    lock : bool, default False
        Whether to read under a shared fcntl lock, for filesystems where
        `O_APPEND` writes can tear (NFS across nodes).
    timeout : float or None, default None
        Seconds to wait for the lock before raising `LockTimeoutError`;
        None waits as long as it takes.

    Returns
    -------
    Callable[[dict], list[dict]]
        Hook `read_churn_notify(ctx)`, returning the file's records.
    """
    return read_hook("churn_notify", lock=lock, timeout=timeout)
