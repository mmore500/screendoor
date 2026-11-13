import json

from ._slot import DEFAULT_SLOT, SlotError, digest


def encode_slot(i: int, record: dict, slot_bytes: int = DEFAULT_SLOT) -> bytes:
    """Encode `record` as the exact `slot_bytes` bytes of slot `i`.

    The record is wrapped in an envelope `{"h": digest, "i": i, "r":
    record}`, padded with spaces and ended with a line feed.

    Parameters
    ----------
    i : int
        The slot's index.
    record : dict
        The record to hold.
    slot_bytes : int, default DEFAULT_SLOT
        The slot size.

    Returns
    -------
    bytes
        The slot's bytes.

    Raises
    ------
    TypeError
        If `record` is not a dict or holds a value JSON cannot represent.
    SlotError
        If the envelope does not fit in `slot_bytes - 1` bytes.
    ValueError
        If `record` holds NaN or infinity.
    """
    if not isinstance(record, dict):
        raise TypeError("record must be a dict (JSON object)")
    envelope = {"h": digest(i, record), "i": i, "r": record}
    text = json.dumps(
        envelope, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode()
    if len(text) > slot_bytes - 1:
        raise SlotError(
            f"envelope is {len(text)} bytes; max is {slot_bytes - 1}"
        )
    return text + b" " * (slot_bytes - 1 - len(text)) + b"\n"
