import json

from ._slot import DEFAULT_SLOT, SlotError, digest


def encode_slot(i: int, record: dict, slot_bytes: int = DEFAULT_SLOT) -> bytes:
    """Return the exact ``slot_bytes`` bytes that hold ``record`` in slot ``i``.

    The record is wrapped in an envelope ``{"h": digest, "i": i, "r":
    record}``, padded with spaces and ended with a line feed. Raises
    SlotError if the envelope does not fit, and ValueError on NaN.
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
