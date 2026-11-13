import typing


def encode_sites(sites: typing.Iterable[int]) -> str:
    """Format a set of sites compactly, with runs as inclusive ranges.

    For example, `{0, 1, 2, 5, 9}` encodes to `"0-2,5,9"`.

    Parameters
    ----------
    sites : iterable of int
        Distinct integers, in any order.

    Returns
    -------
    str
        Comma-separated integers and `a-b` ranges, ascending.
    """
    runs: list = []
    for i in sorted(sites):
        if runs and i == runs[-1][1] + 1:
            runs[-1][1] = i
        else:
            runs.append([i, i])
    return ",".join(f"{a}" if a == b else f"{a}-{b}" for a, b in runs)
