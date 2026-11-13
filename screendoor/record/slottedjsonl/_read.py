from ._decode_slot import decode_slot
from ._resolve_slot import resolve_slot


def read(
    path: str, n: int | None = None, slot_bytes: int | None = None
) -> dict[int, dict]:
    """Read the valid slots of `path`, as `{index: record}`.

    A partial last slot is not valid.

    Parameters
    ----------
    path : str
        The slotted file.
    n : int or None, default None
        How many slots to read, from the first; None reads them all.
    slot_bytes : int or None, default None
        The slot size; None takes the file's own.

    Returns
    -------
    dict of {int: dict}
        Each valid slot's record, by index.
    """
    slot_bytes = resolve_slot(path, slot_bytes)
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
