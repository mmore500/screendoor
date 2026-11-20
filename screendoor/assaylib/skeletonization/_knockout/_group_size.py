import math
import typing


def group_size(outcomes: typing.Iterable[tuple[int, bool]]) -> int:
    """Pick how many sites to test together, from how groups have fared.

    Fits the chance `q` that a site passes, taking sites as independent,
    so that a group of `size` passes with chance `q ** size`. The largest
    power of two that still passes half the time is the size that settles
    the most sites per test; where under about 0.7 of sites pass, it is 1.

    Parameters
    ----------
    outcomes : iterable of tuple of (int, bool)
        The size of each group tested, and whether it passed.

    Returns
    -------
    int
        The group size, a power of two.
    """
    outcomes = list(outcomes)

    def log_likelihood(q: float) -> float:
        return sum(
            size * math.log(q) if passed else math.log1p(-(q**size))
            for size, passed in outcomes
        )

    q = max((i / 1000 for i in range(1, 1000)), key=log_likelihood)
    return 2 ** max(0, math.floor(math.log2(math.log(0.5) / math.log(q))))
