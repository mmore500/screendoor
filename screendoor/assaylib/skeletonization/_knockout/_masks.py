ACCEPT, REJECT, UNKNOWN = "accept", "reject", "unknown"


def split(sites: list, k: int) -> list:
    """Cut ``sites`` into ``k`` consecutive, near-equal chunks."""
    m = len(sites)
    return [frozenset(sites[i * m // k : (i + 1) * m // k]) for i in range(k)]


def singletons(sites) -> list:
    return [frozenset([i]) for i in sites]


def accepted_sites(outcomes: dict) -> list:
    return sorted(i for d, v in outcomes.items() if v == ACCEPT for i in d)
