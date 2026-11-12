import hashlib

from ..auxlib._canonical_json import canonical_json


def derive_seed(*parts) -> int:
    """32-bit seed from the canonical JSON of ``parts``.

    32 bits fit the seed argument of nearly any program, and JSON numbers.
    """
    digest = hashlib.sha256(canonical_json(list(parts)).encode()).digest()
    return int.from_bytes(digest[:4], "big")
