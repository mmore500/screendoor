ACCEPT, REJECT, UNKNOWN = "accept", "reject", "unknown"


def split(sites: list[int], k: int) -> list[frozenset]:
    """Cut ``sites`` into ``k`` consecutive, near-equal chunks.

    Parameters
    ----------
    sites : list of int
        The sites, in order.
    k : int
        How many chunks.

    Returns
    -------
    list of frozenset
        The chunks, in order; some are empty if ``k`` exceeds the sites.
    """
    m = len(sites)
    return [frozenset(sites[i * m // k : (i + 1) * m // k]) for i in range(k)]


def singletons(sites: list[int]) -> list[frozenset]:
    """One mask per site.

    Parameters
    ----------
    sites : list of int
        The sites, in order.

    Returns
    -------
    list of frozenset
        ``{site}`` for each site, in order.
    """
    return [frozenset([i]) for i in sites]


def accepted_sites(outcomes: dict[frozenset, str]) -> list[int]:
    """The sites in any accepted mask.

    Parameters
    ----------
    outcomes : dict of {frozenset: str}
        The verdict on each mask.

    Returns
    -------
    list of int
        The sites of the accepted masks, sorted.
    """
    return sorted(i for d, v in outcomes.items() if v == ACCEPT for i in d)
