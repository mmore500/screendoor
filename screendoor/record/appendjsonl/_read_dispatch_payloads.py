import typing

from ._files import read_hook


def read_dispatch_payloads(
    *, lock: bool = False, timeout: float | None = None
) -> typing.Callable[[dict], list[dict]]:
    """Create a `how_read_dispatch_payloads` hook that reads the
    dispatchdir's `dispatch_payloads.jsonl`.

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
        Hook `read_dispatch_payloads(ctx)`, returning the file's records.
    """
    return read_hook("dispatch_payloads", lock=lock, timeout=timeout)
