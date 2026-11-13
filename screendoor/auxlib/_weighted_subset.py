import math
import random
import typing


def weighted_subset(
    sites: typing.Collection[int],
    size: int,
    weights: dict[int, float],
    rng: random.Random,
) -> frozenset[int]:
    """Sample `size` of `sites` without replacement, favoring heavier
    sites.

    Each site draws an exponential clock with rate equal to its weight, and
    the `size` earliest clocks are taken.

    Parameters
    ----------
    sites : collection of int
        The sites to sample from.
    size : int
        How many sites to sample.
    weights : dict of {int: float}
        Weight of each site; a site absent from `weights` has weight 1.
    rng : random.Random
        Source of randomness.

    Returns
    -------
    frozenset of int
        The sampled sites.

    Raises
    ------
    ValueError
        If `size` is negative or exceeds `len(sites)`.
    """
    if not 0 <= size <= len(sites):
        raise ValueError("invalid subset size")
    clocks = sorted(
        (-math.log(max(rng.random(), 1e-300)) / weights.get(i, 1.0), i)
        for i in sorted(sites)
    )
    return frozenset(i for _, i in clocks[:size])
