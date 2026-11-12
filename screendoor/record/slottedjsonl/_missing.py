from ._read import read


def missing(path: str, n: int, slot_bytes: int | None = None) -> list[int]:
    """Return the sorted indices in ``0..n-1`` whose slots are not valid.

    Rerunning the writers for exactly these indices is always safe.

    Parameters
    ----------
    path : str
        The slotted file.
    n : int
        How many slots there should be.
    slot_bytes : int or None, default None
        The slot size; None takes the file's own.

    Returns
    -------
    list of int
        The indices of the slots not valid.
    """
    valid = read(path, n, slot_bytes)
    return [i for i in range(n) if i not in valid]
