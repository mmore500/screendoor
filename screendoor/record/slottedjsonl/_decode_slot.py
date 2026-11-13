import json

from ._slot import digest


def decode_slot(i: int, raw: bytes) -> dict | None:
    """Decode the record held in the bytes of slot `i`.

    A slot is valid when its bytes parse as an envelope whose index is `i`
    and whose digest matches its record. Empty, torn, mixed and misplaced
    slots are all invalid.

    Parameters
    ----------
    i : int
        The slot's index.
    raw : bytes
        The slot's bytes.

    Returns
    -------
    dict or None
        The record, or None if the slot is not valid.
    """
    try:
        envelope = json.loads(raw.replace(b"\0", b"").strip())
        if envelope["i"] != i or not isinstance(envelope["r"], dict):
            return None
        if digest(i, envelope["r"]) != envelope["h"]:
            return None
    except (ValueError, TypeError, KeyError):
        return None  # not JSON, not an object, or lacking h, i or r
    return envelope["r"]
