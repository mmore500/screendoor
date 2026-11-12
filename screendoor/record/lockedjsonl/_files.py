import os

from ...auxlib._append_jsonl_line import run_after_append_hooks, stamp
from ...auxlib._canonical_json import canonical_json
from ...auxlib._read_jsonl_tolerant import parse_jsonl_tolerant
from ..appendjsonl._files import (
    DISPATCH_PAYLOADS_FILE as DISPATCH_PAYLOADS_FILE,
)
from ..appendjsonl._files import (
    DISPATCH_SUBMISSIONS_FILE as DISPATCH_SUBMISSIONS_FILE,
)
from ..appendjsonl._files import (
    DISPATCH_TELEMETRY_FILE as DISPATCH_TELEMETRY_FILE,
)
from ..appendjsonl._files import path as path
from ._locked_open import locked_open


def append(file: str, record: dict, timeout: float | None = None) -> dict:
    """Append ``record`` (a dict with "event") as one line, under an
    exclusive lock; stamp schema and ts and return it.

    A last line left unterminated by a writer that died mid-write is ended
    first, so the new line is not spliced onto it.

    Parameters
    ----------
    file : str
        The JSONL file, made if missing.
    record : dict
        The record to append.
    timeout : float or None, default None
        Seconds to wait for the lock; None waits as long as it takes.

    Returns
    -------
    dict
        ``record`` as stamped.

    Raises
    ------
    LockTimeoutError
        If the lock is not had within ``timeout`` seconds.
    """
    out = stamp(record)
    line = (canonical_json(out) + "\n").encode()
    os.makedirs(os.path.dirname(os.path.abspath(file)), exist_ok=True)
    flags = os.O_RDWR | os.O_APPEND | os.O_CREAT
    with locked_open(file, flags, exclusive=True, timeout=timeout) as fd:
        size = os.fstat(fd).st_size
        if size and os.pread(fd, 1, size - 1) != b"\n":
            line = b"\n" + line
        view = memoryview(line)
        while view:
            view = view[os.write(fd, view) :]
    run_after_append_hooks(file, out)
    return out


def read_events(file: str, timeout: float | None = None) -> list[dict]:
    """Read every whole record, under a shared lock; [] if no file.

    Parameters
    ----------
    file : str
        The JSONL file.
    timeout : float or None, default None
        Seconds to wait for the lock; None waits as long as it takes.

    Returns
    -------
    list of dict
        The records, in file order, skipping torn lines.

    Raises
    ------
    LockTimeoutError
        If the lock is not had within ``timeout`` seconds.
    SchemaTooNewError
        If a record's schema is newer than this code understands.
    """
    try:
        with locked_open(
            file, os.O_RDONLY, exclusive=False, timeout=timeout
        ) as fd:
            chunks = []
            while chunk := os.read(fd, 1 << 20):
                chunks.append(chunk)
    except FileNotFoundError:
        return []
    return parse_jsonl_tolerant(b"".join(chunks), file)
