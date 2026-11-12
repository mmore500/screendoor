import typing


def encode_sites(sites: typing.Iterable[int]) -> str:
    """Sorted integers as compact ranges, e.g. ``{0, 1, 2, 5, 9}`` ->
    "0-2,5,9".

    Parameters
    ----------
    sites : iterable of int
        Distinct integers, in any order.

    Returns
    -------
    str
        Comma-separated integers, runs as inclusive ``a-b`` ranges.
    """
    runs: list = []
    for i in sorted(sites):
        if runs and i == runs[-1][1] + 1:
            runs[-1][1] = i
        else:
            runs.append([i, i])
    return ",".join(f"{a}" if a == b else f"{a}-{b}" for a, b in runs)
