import os

from ._slot import DEFAULT_SLOT, check_slot, placeholder


def init(path: str, n: int, slot_bytes: int = DEFAULT_SLOT) -> None:
    """Create a file of ``n`` placeholder slots; fail if ``path`` exists.

    Must finish before any writer for those slots starts.
    """
    check_slot(slot_bytes)
    with open(path, "xb") as fh:
        for _ in range(n):
            fh.write(placeholder(slot_bytes))
        fh.flush()
        os.fsync(fh.fileno())
