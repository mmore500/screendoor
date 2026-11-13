import typing

from ._files import read_hook


def read_trial_submissions(
    *, lock: bool = False, timeout: float | None = None
) -> typing.Callable[[dict], list[dict]]:
    """Create a `how_read_trial_submissions` hook that reads the run
    directory's `trial_submissions.jsonl`.

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
        Hook `read_trial_submissions(ctx)`, returning the file's records.
    """
    return read_hook("trial_submissions", lock=lock, timeout=timeout)
