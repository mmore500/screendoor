import hashlib
import json
import os

DEFAULT_SLOT = 32768  # bytes: eight 4096-byte pages


class SlotError(Exception):
    """A record does not fit its slot, or the slot could not be written."""


def check_slot(slot_bytes: int) -> None:
    """Slots are whole memory pages, so no two share one.

    Parameters
    ----------
    slot_bytes : int
        The slot size to check.

    Raises
    ------
    ValueError
        If ``slot_bytes`` is not a positive multiple of 4096.
    """
    if slot_bytes <= 0 or slot_bytes % 4096:
        raise ValueError("slot size must be a positive multiple of 4096")


def placeholder(slot_bytes: int) -> bytes:
    """The bytes of an unfilled slot: ``null``, spaces, a line feed.

    Parameters
    ----------
    slot_bytes : int
        The slot size.

    Returns
    -------
    bytes
        The slot's bytes.
    """
    return b"null" + b" " * (slot_bytes - 5) + b"\n"


def digest(i: int, record: dict) -> str:
    """BLAKE2b-64 of the canonical JSON of ``[i, record]``, as hex.

    Parameters
    ----------
    i : int
        The slot's index.
    record : dict
        The record in the slot.

    Returns
    -------
    str
        16 hex digits.

    Raises
    ------
    TypeError
        If ``record`` holds a value JSON cannot represent.
    ValueError
        If ``record`` holds NaN or infinity.
    """
    payload = json.dumps(
        [i, record],
        separators=(",", ":"),
        sort_keys=True,
        ensure_ascii=True,
        allow_nan=False,
    )
    return hashlib.blake2b(payload.encode(), digest_size=8).hexdigest()


def pwrite_all(fd: int, buf: bytes, offset: int) -> None:
    """Write all of ``buf`` at ``offset`` in one ``pwrite``.

    Parameters
    ----------
    fd : int
        The file to write.
    buf : bytes
        The bytes to write.
    offset : int
        Where in the file to write them.

    Raises
    ------
    SlotError
        If the write is short.
    """
    n = os.pwrite(fd, buf, offset)
    if n != len(buf):
        raise SlotError(f"short write: {n} of {len(buf)} bytes")
