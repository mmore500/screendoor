import json

from ._slot import digest


def decode_slot(i: int, raw: bytes) -> dict | None:
    """Return the record in slot ``i``'s bytes; None unless it is valid.

    A slot is valid if it parses as an envelope whose index is ``i`` and
    whose digest matches its record. Empty, torn, mixed and misplaced
    slots all give None.
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
