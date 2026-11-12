import os

from ...auxlib._append_jsonl_line import SCHEMA, _after_append_hooks
from ...auxlib._canonical_json import canonical_json
from ...auxlib._now_iso import now_iso
from ...auxlib._read_jsonl_tolerant import parse_jsonl_tolerant
from ..jsonl._files import DISPATCH_FILE as DISPATCH_FILE
from ..jsonl._files import path as path
from ._locked_open import locked_open


def append(file: str, record: dict, timeout: float | None = None) -> dict:
    """Append ``record`` (a dict with "event") as one line, under an
    exclusive lock; stamp schema and ts and return it.

    A last line left unterminated by a writer that died mid-write is ended
    first, so the new line is not spliced onto it.
    """
    fields = {
        k: v for k, v in record.items() if k not in ("schema", "ts", "event")
    }
    out = {"schema": SCHEMA, "ts": now_iso(), "event": record["event"]}
    out.update(fields)
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
    for hook in list(_after_append_hooks):
        hook(file, out)
    return out


def read_events(file: str, timeout: float | None = None) -> list[dict]:
    """Read every whole record, under a shared lock; [] if no file."""
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
