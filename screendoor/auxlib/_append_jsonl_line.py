import os

from ._canonical_json import canonical_json
from ._now_iso import now_iso

# called as hook(path, record) after each append; crash-injection tests use it
_after_append_hooks: list = []


def stamp(record: dict) -> dict:
    """Return a copy of `record` led by a fresh `ts`, then its `event`.

    Parameters
    ----------
    record : dict
        A record with an `event` field; any `ts` it has is replaced.

    Returns
    -------
    dict
        The stamped copy.
    """
    fields = {k: v for k, v in record.items() if k not in ("ts", "event")}
    return {"ts": now_iso(), "event": record["event"], **fields}


def run_after_append_hooks(path: str, record: dict) -> None:
    """Call each registered after-append hook as `hook(path, record)`."""
    for hook in list(_after_append_hooks):
        hook(path, record)


def append_jsonl_line(path: str, record: dict) -> dict:
    """Append `record`, stamped, to the JSONL file `path` as one line
    written in a single `write()`.

    Parameters
    ----------
    path : str
        The JSONL file; it and its directories are created if missing.
    record : dict
        A record with an `event` field.

    Returns
    -------
    dict
        The record as stamped and written.

    Raises
    ------
    OSError
        If the line is not written whole.
    """
    record = stamp(record)
    line = (canonical_json(record) + "\n").encode()
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        if os.write(fd, line) != len(line):  # pragma: no cover
            raise OSError(f"short write to {path}")
    finally:
        os.close(fd)
    run_after_append_hooks(path, record)
    return record
