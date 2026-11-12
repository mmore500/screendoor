from ._read import read


def missing(path: str, n: int, slot_bytes: int | None = None) -> list:
    """Return the sorted indices in ``0..n-1`` whose slots are not valid.

    Rerunning the writers for exactly these indices is always safe.
    """
    valid = read(path, n, slot_bytes)
    return [i for i in range(n) if i not in valid]
