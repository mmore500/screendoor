import typing

from ._files import write_hook


def write_dispatch_telemetry(
    *, lock: bool = False, timeout: float | None = None
) -> typing.Callable[[dict, dict], dict]:
    """Create a `how_write_dispatch_telemetry` hook that appends to the
    dispatchdir's `dispatch_telemetry.jsonl`.

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
        Hook `write_dispatch_telemetry(ctx, record)`, returning the record
        as stamped and written.
    """
    return write_hook("dispatch_telemetry", lock=lock, timeout=timeout)
