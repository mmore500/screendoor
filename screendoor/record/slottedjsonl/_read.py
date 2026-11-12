from ._decode_slot import decode_slot
from ._slot import DEFAULT_SLOT, check_slot


def read(
    path: str, n: int | None = None, slot_bytes: int = DEFAULT_SLOT
) -> dict:
    """Return ``{index: record}`` for the valid slots.

    With ``n``, only indices below ``n`` are read. A partial last slot is
    not valid.
    """
    check_slot(slot_bytes)
    records = {}
    with open(path, "rb") as fh:
        i = 0
        while n is None or i < n:
            raw = fh.read(slot_bytes)
            if len(raw) < slot_bytes:  # end of file, or a partial last slot
                break
            record = decode_slot(i, raw)
            if record is not None:
                records[i] = record
            i += 1
    return records
