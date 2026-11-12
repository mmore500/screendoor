import os

from ._canonical_json import canonical_json
from ._now_iso import now_iso

SCHEMA = 1

# called as hook(path, record) after each append; for crash-injection tests
_after_append_hooks: list = []


def stamp(record: dict) -> dict:
    """``record`` (a dict with "event") with a fresh ``schema`` and ``ts``
    in front, replacing any it had.

    Parameters
    ----------
    record : dict
        The record to stamp.

    Returns
    -------
    dict
        A copy, led by ``schema``, ``ts`` and ``event``.
    """
    fields = {
        k: v for k, v in record.items() if k not in ("schema", "ts", "event")
    }
    return {
        "schema": SCHEMA,
        "ts": now_iso(),
        "event": record["event"],
        **fields,
    }


def run_after_append_hooks(path: str, record: dict) -> None:
    """Call each after-append hook as ``hook(path, record)``.

    Parameters
    ----------
    path : str
        The file appended to.
    record : dict
        The record appended, as stamped.
    """
    for hook in list(_after_append_hooks):
        hook(path, record)


def append_jsonl_line(path: str, record: dict) -> dict:
    """Append ``record`` (a dict with "event"), stamped, as one line in a
    single ``write()``; return it as stamped.

    Parameters
    ----------
    path : str
        The JSONL file, created with its directories if missing.
    record : dict
        The record to append.

    Returns
    -------
    dict
        The record as stamped.

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
