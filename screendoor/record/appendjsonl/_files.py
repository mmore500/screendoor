import os
import typing

from ...auxlib._append_jsonl_line import (
    append_jsonl_line,
    run_after_append_hooks,
    stamp,
)
from ...auxlib._canonical_json import canonical_json
from ...auxlib._read_jsonl_tolerant import (
    parse_jsonl_tolerant,
    read_jsonl_tolerant,
)
from ._locked_open import locked_open


def record_path(ctx: dict, name: str) -> str:
    """Return the path of the record file `name` of the dispatch `ctx`.

    Dispatch records (`dispatch_submissions`, `dispatch_payloads` and
    `dispatch_telemetry`) live in the dispatchdir; trial and churn records
    live in the dispatch's run directory.

    Parameters
    ----------
    ctx : dict
        The hook context.
    name : str
        The record file's name, without `.jsonl`.

    Returns
    -------
    str
        The file's path.
    """
    where = "dispatchdir" if name.startswith("dispatch_") else "run_dir"
    return os.path.join(ctx[where], f"{name}.jsonl")


def append(
    path: str,
    record: dict,
    *,
    lock: bool = False,
    timeout: float | None = None,
) -> dict:
    """Append `record`, stamped, as one line of the JSONL file `path`.

    Without `lock`, the line goes out in a single `O_APPEND` write. With
    it, the write holds an exclusive fcntl lock, and a last line left
    unterminated by a writer that died mid-write is ended first, so that
    the new line is not spliced onto it.

    Parameters
    ----------
    path : str
        The JSONL file; it and its directories are created if missing.
    record : dict
        A record with an `event` field.
    lock : bool, default False
        Whether to write under an exclusive fcntl lock.
    timeout : float or None, default None
        Seconds to wait for the lock before raising `LockTimeoutError`;
        None waits as long as it takes.

    Returns
    -------
    dict
        The record as stamped and written.

    Raises
    ------
    LockTimeoutError
        If the lock is not acquired within `timeout` seconds.
    """
    if not lock:
        return append_jsonl_line(path, record)
    record = stamp(record)
    line = (canonical_json(record) + "\n").encode()
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    flags = os.O_RDWR | os.O_APPEND | os.O_CREAT
    with locked_open(path, flags, exclusive=True, timeout=timeout) as fd:
        size = os.fstat(fd).st_size
        if size and os.pread(fd, 1, size - 1) != b"\n":
            line = b"\n" + line
        view = memoryview(line)
        while view:
            view = view[os.write(fd, view) :]
    run_after_append_hooks(path, record)
    return record


def read(
    path: str, *, lock: bool = False, timeout: float | None = None
) -> list[dict]:
    """Read every record in the JSONL file `path`, skipping torn lines.

    Parameters
    ----------
    path : str
        The JSONL file; a missing file reads as empty.
    lock : bool, default False
        Whether to read under a shared fcntl lock.
    timeout : float or None, default None
        Seconds to wait for the lock before raising `LockTimeoutError`;
        None waits as long as it takes.

    Returns
    -------
    list of dict
        The records, in file order.

    Raises
    ------
    LockTimeoutError
        If the lock is not acquired within `timeout` seconds.
    """
    if not lock:
        return read_jsonl_tolerant(path)
    try:
        with locked_open(
            path, os.O_RDONLY, exclusive=False, timeout=timeout
        ) as fd:
            chunks = []
            while chunk := os.read(fd, 1 << 20):
                chunks.append(chunk)
    except FileNotFoundError:
        return []
    return parse_jsonl_tolerant(b"".join(chunks), path)


def read_hook(
    name: str, *, lock: bool, timeout: float | None
) -> typing.Callable[[dict], list[dict]]:
    """Make a `how_read_<name>` hook that reads the record file `name`
    with `read`."""

    def hook(ctx: dict) -> list[dict]:
        return read(record_path(ctx, name), lock=lock, timeout=timeout)

    return hook


def write_hook(
    name: str, *, lock: bool, timeout: float | None
) -> typing.Callable[[dict, dict], dict]:
    """Make a `how_write_<name>` hook that appends to the record file
    `name` with `append`."""

    def hook(ctx: dict, record: dict) -> dict:
        return append(
            record_path(ctx, name), record, lock=lock, timeout=timeout
        )

    return hook
