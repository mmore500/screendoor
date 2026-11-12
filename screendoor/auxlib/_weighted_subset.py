from __future__ import annotations

import math
import typing

if typing.TYPE_CHECKING:
    import random


def weighted_subset(
    sites: typing.Collection[int],
    size: int,
    weights: dict[int, float],
    rng: random.Random,
) -> frozenset[int]:
    """Weighted sampling without replacement, by exponential clocks.

    Parameters
    ----------
    sites : collection of int
        The sites to sample from.
    size : int
        How many to sample.
    weights : dict
        Weight by site; a site not in it weighs 1.
    rng : random.Random
        The source of randomness.

    Returns
    -------
    frozenset of int
        ``size`` of ``sites``, heavier ones likelier.

    Raises
    ------
    ValueError
        If ``size`` is negative or more than ``len(sites)``.
    """
    if not 0 <= size <= len(sites):
        raise ValueError("invalid subset size")
    clocks = sorted(
        (-math.log(max(rng.random(), 1e-300)) / weights.get(i, 1.0), i)
        for i in sorted(sites)
    )
    return frozenset(i for _, i in clocks[:size])
