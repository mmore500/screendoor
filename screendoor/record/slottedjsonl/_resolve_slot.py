from ._slot import DEFAULT_SLOT, check_slot


def file_slot(path: str) -> int | None:
    """Find the slot size a slotted file was made with: the length of its
    first line.

    Parameters
    ----------
    path : str
        The slotted file.

    Returns
    -------
    int or None
        The slot size in bytes, or None if the file is missing or has no
        complete first slot yet.
    """
    try:
        with open(path, "rb") as fh:
            head = b""
            while b"\n" not in head:
                chunk = fh.read(4096)
                if not chunk:
                    return None
                head += chunk
    except FileNotFoundError:
        return None
    return head.index(b"\n") + 1


def resolve_slot(path: str, slot_bytes: int | None) -> int:
    """Decide the slot size to use for `path`.

    Parameters
    ----------
    path : str
        The slotted file, made or not.
    slot_bytes : int or None
        The slot size asked for; None takes the file's own, or
        `DEFAULT_SLOT` for a file not yet made.

    Returns
    -------
    int
        The slot size in bytes.

    Raises
    ------
    ValueError
        If `slot_bytes` is not a positive multiple of 4096, or differs from
        the file's.
    """
    found = file_slot(path)
    if slot_bytes is None:
        return found or DEFAULT_SLOT
    check_slot(slot_bytes)
    if found is not None and found != slot_bytes:
        raise ValueError(f"{path} has {found}-byte slots, not {slot_bytes}")
    return slot_bytes
