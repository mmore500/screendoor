import math


def weighted_subset(sites, size: int, weights: dict, rng) -> frozenset:
    """Weighted sampling without replacement, by exponential clocks."""
    if not 0 <= size <= len(sites):
        raise ValueError("invalid subset size")
    clocks = sorted(
        (-math.log(max(rng.random(), 1e-300)) / weights.get(i, 1.0), i)
        for i in sorted(sites)
    )
    return frozenset(i for _, i in clocks[:size])
