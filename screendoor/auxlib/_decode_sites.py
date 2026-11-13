def decode_sites(text: str) -> frozenset[int]:
    """Parse a set of sites from the range notation of `encode_sites`.

    For example, `"0-2,5,9"` decodes to `{0, 1, 2, 5, 9}`.

    Parameters
    ----------
    text : str
        Comma-separated integers and inclusive `a-b` ranges.

    Returns
    -------
    frozenset of int
        The sites.
    """
    sites: set = set()
    for part in filter(None, text.split(",")):
        a, _, b = part.partition("-")
        sites.update(range(int(a), int(b or a) + 1))
    return frozenset(sites)
