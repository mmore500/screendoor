import os

from ._canonical_json import canonical_json
from ._now_iso import now_iso

SCHEMA = 1

# called as hook(path, record) after each append; for crash-injection tests
_after_append_hooks: list = []


def append_jsonl_line(path: str, event: str, **fields) -> dict:
    """Append one record as one line in a single ``write()``; return it."""
    record = {"schema": SCHEMA, "ts": now_iso(), "event": event, **fields}
    line = (canonical_json(record) + "\n").encode()
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        if os.write(fd, line) != len(line):  # pragma: no cover
            raise OSError(f"short write to {path}")
    finally:
        os.close(fd)
    for hook in list(_after_append_hooks):
        hook(path, record)
    return record
