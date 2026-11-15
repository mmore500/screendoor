import math


def fit_effects(
    knockouts: list[frozenset[int]],
    losses: list[float],
    sites: list[int],
) -> tuple[dict[int, float], float]:
    """Estimate each site's cost from the losses of knockouts of several
    sites at once.

    Fits `loss = sum of the costs of the sites knocked out` by least
    squares, with conjugate gradients on the normal equations.

    Parameters
    ----------
    knockouts : list of frozenset of int
        The sites knocked out in each trial.
    losses : list of float
        Each trial's loss against the wildtype.
    sites : list of int
        The sites to estimate, which the knockouts were drawn from.

    Returns
    -------
    dict of {int: float}
        Each site's estimated cost; it may be negative.
    float
        The costs' standard error, about the same for every site of a
        random design; infinite with fewer trials than sites.
    """
    column = {site: j for j, site in enumerate(sites)}
    rows = [[column[i] for i in deleted] for deleted in knockouts]

    def forward(v: list[float]) -> list[float]:
        return [sum(v[j] for j in row) for row in rows]

    def backward(u: list[float]) -> list[float]:
        out = [0.0] * len(sites)
        for row, x in zip(rows, u):
            for j in row:
                out[j] += x
        return out

    effects = [0.0] * len(sites)
    residual = list(losses)
    gradient = backward(residual)
    step = list(gradient)
    norm = start = sum(g * g for g in gradient)
    for _ in range(4 * len(sites)):
        if norm <= 1e-20 * start or norm == 0.0:
            break
        moved = forward(step)
        scale = norm / sum(m * m for m in moved)
        effects = [e + scale * s for e, s in zip(effects, step)]
        residual = [r - scale * m for r, m in zip(residual, moved)]
        gradient = backward(residual)
        last, norm = norm, sum(g * g for g in gradient)
        step = [g + norm / last * s for g, s in zip(gradient, step)]

    trials, spare = len(rows), len(rows) - len(sites)
    counts = backward([1.0] * trials)
    # what each site's own trials tell of it: out in some, in for the rest
    told = [c * (1.0 - c / trials) for c in counts if 0.0 < c < trials]
    if spare <= 0 or not told:
        return dict(zip(sites, effects)), math.inf
    variance = sum(r * r for r in residual) / spare
    error = math.sqrt(variance / (sum(told) / len(told)) * trials / spare)
    return dict(zip(sites, effects)), error
