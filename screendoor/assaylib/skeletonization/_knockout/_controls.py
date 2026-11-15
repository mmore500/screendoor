import math
from statistics import fmean, stdev

CONTROL_TESTS = ("mean", "t", "rank")
RULES = ("detectable_loss", "noninferiority")


def _betacf(a: float, b: float, x: float) -> float:
    """Evaluate the continued fraction of the incomplete beta function, by
    Lentz's method."""
    tiny = 1e-300

    def clamp(v: float) -> float:
        return v if abs(v) >= tiny else tiny

    c, d = 1.0, 1.0 / clamp(1.0 - (a + b) * x / (a + 1.0))
    h = d
    for m in range(1, 1000):
        for aa in (
            m * (b - m) * x / ((a + 2 * m - 1) * (a + 2 * m)),
            -(a + m) * (a + b + m) * x / ((a + 2 * m) * (a + 2 * m + 1)),
        ):
            d = 1.0 / clamp(1.0 + aa * d)
            c = clamp(1.0 + aa / c)
            h *= d * c
        if abs(d * c - 1.0) < 1e-15:
            break
    return h


def _betainc(a: float, b: float, x: float) -> float:
    """Evaluate the regularized incomplete beta function I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    front = math.exp(
        math.lgamma(a + b)
        - math.lgamma(a)
        - math.lgamma(b)
        + a * math.log(x)
        + b * math.log1p(-x)
    )
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def t_cdf(t: float, df: float) -> float:
    """Evaluate Student's t distribution function.

    Parameters
    ----------
    t : float
        The statistic.
    df : float
        Degrees of freedom.

    Returns
    -------
    float
        The probability of a statistic at most `t`.
    """
    tail = 0.5 * _betainc(df / 2.0, 0.5, df / (df + t * t))
    return 1.0 - tail if t > 0 else tail


def t_quantile(p: float, df: float) -> float:
    """Evaluate Student's t quantile function, by bisection on `t_cdf`.

    Parameters
    ----------
    p : float
        A probability, strictly between 0 and 1.
    df : float
        Degrees of freedom, positive.

    Returns
    -------
    float
        The statistic `t` with `t_cdf(t, df) == p`.

    Raises
    ------
    ValueError
        If `p` or `df` is out of range.
    """
    if not 0.0 < p < 1.0 or df <= 0:
        raise ValueError("t_quantile needs 0 < p < 1 and df > 0")
    hi = 1.0
    while t_cdf(hi, df) < p:
        hi *= 2.0
    lo = -hi
    while t_cdf(lo, df) > p:
        lo *= 2.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if t_cdf(mid, df) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def beta_quantile(p: float, a: float, b: float) -> float:
    """Evaluate the beta distribution's quantile function, by bisection.

    Parameters
    ----------
    p : float
        A probability, strictly between 0 and 1.
    a : float
        The first shape parameter, positive.
    b : float
        The second shape parameter, positive.

    Returns
    -------
    float
        The value `x` that a beta variable is at most with probability
        `p`.

    Raises
    ------
    ValueError
        If `p`, `a` or `b` is out of range.
    """
    if not 0.0 < p < 1.0 or a <= 0 or b <= 0:
        raise ValueError("beta_quantile needs 0 < p < 1, a > 0 and b > 0")
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if _betainc(a, b, mid) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def _gammainc(a: float, x: float) -> float:
    """Evaluate the regularized lower incomplete gamma function P(a, x)."""
    if x <= 0.0:
        return 0.0
    front = math.exp(a * math.log(x) - x - math.lgamma(a))
    if x < a + 1.0:  # the series
        term = total = 1.0 / a
        for k in range(1, 100000):
            term *= x / (a + k)
            total += term
            if term < total * 1e-16:
                break
        return front * total
    tiny = 1e-300  # else the upper function's continued fraction, by Lentz

    def clamp(v: float) -> float:
        return v if abs(v) >= tiny else tiny

    b = x + 1.0 - a
    c, d = 1.0 / tiny, 1.0 / b
    h = d
    for i in range(1, 100000):
        an = -i * (i - a)
        b += 2.0
        d = 1.0 / clamp(an * d + b)
        c = clamp(b + an / c)
        h *= d * c
        if abs(d * c - 1.0) < 1e-15:
            break
    return 1.0 - front * h


def chi2_quantile(p: float, df: float) -> float:
    """Evaluate the chi-square quantile function, by bisection.

    Parameters
    ----------
    p : float
        A probability, strictly between 0 and 1.
    df : float
        Degrees of freedom, positive.

    Returns
    -------
    float
        The statistic `x` that a chi-square variable is at most with
        probability `p`.

    Raises
    ------
    ValueError
        If `p` or `df` is out of range.
    """
    if not 0.0 < p < 1.0 or df <= 0:
        raise ValueError("chi2_quantile needs 0 < p < 1 and df > 0")
    lo, hi = 0.0, float(df)
    while _gammainc(df / 2.0, hi / 2.0) < p:
        hi *= 2.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if _gammainc(df / 2.0, mid / 2.0) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def _rank_sum_counts(r: int, n: int) -> list:
    """Count the orderings of `r` candidates among `n` controls that give
    each value of U, the number of pairs in which the candidate is the
    larger, for U from 0 to `r * n`."""
    # f[j][u]: orderings of i candidates and j controls with that U
    f = [[1] for _ in range(n + 1)]  # i = 0: U is 0
    for _ in range(r):
        g = [[1]]  # no controls: U is 0
        for j in range(1, n + 1):
            # the largest is a control (adds 0) or a candidate (adds j)
            left, top = g[j - 1], f[j]
            size = max(len(left), len(top) + j)
            row = [0] * size
            for u, k in enumerate(left):
                row[u] += k
            for u, k in enumerate(top):
                row[u + j] += k
            g.append(row)
        f = g
    return f[n]


def rank_pvalue(
    scores: list[float], controls: list[float], *, upper: bool = False
) -> float:
    """Compute the one-sided exact Mann-Whitney p-value that `scores` come
    from a distribution below the controls' or, with `upper`, above it.

    Ties count against the alternative.

    Parameters
    ----------
    scores : list of float
        A candidate's replicate scores.
    controls : list of float
        The controls' scores.
    upper : bool, default False
        Whether the alternative is that the candidate scores higher.

    Returns
    -------
    float
        The p-value.
    """
    counts = _rank_sum_counts(len(scores), len(controls))
    if upper:
        u = sum(c < x for x in scores for c in controls)
        return sum(counts[u:]) / sum(counts)
    u = sum(c <= x for x in scores for c in controls)
    return sum(counts[: u + 1]) / sum(counts)


class Controls:
    """The wildtype controls' scores, and the rules that judge a
    candidate's replicate scores against them.

    `limit` is the controls' mean less the tolerance, `mean * (1 - rel_tol)
    - abs_tol`, and `margin` is how far below the mean it lies. Each rule
    has a one-sided `alpha`:

    * `detectable_loss` rejects only a candidate whose scores are
      significantly below `limit`.
    * `noninferiority` accepts only a candidate whose scores are
      significantly above `limit`, which shows it loses less than `margin`.

    Scores are compared by `control_test`: `t`, a one-sided t prediction
    bound and the default with two or more controls; `rank`, a one-sided
    exact Mann-Whitney test of the replicates, shifted up by the tolerance,
    against the controls; or `mean`, accepting a mean of at least `limit`
    and the default with one control. If every control has the same score,
    there is no noise to test against, and every rule accepts just the
    candidates whose mean is at least `limit`.

    Parameters
    ----------
    kw : dict
        The assay's kwargs: `control_test`, `rel_tol` and `abs_tol`.
    scores : list of float
        The controls' scores.

    Raises
    ------
    ValueError
        If `control_test` is unknown, or `t` with fewer than two controls.
    """

    def __init__(self, kw: dict, scores: list) -> None:
        self.scores = [float(x) for x in scores]
        self.n = n = len(self.scores)
        self.test = kw.get("control_test", "t" if n >= 2 else "mean")
        if self.test not in CONTROL_TESTS:
            raise ValueError(f"control_test must be one of {CONTROL_TESTS}")
        if self.test == "t" and n < 2:
            raise ValueError("control_test 't' needs at least 2 controls")
        self.mean = fmean(self.scores)
        self.sd = stdev(self.scores, self.mean) if n >= 2 else None
        rel, tol = kw.get("rel_tol", 0.0), kw.get("abs_tol", 0.0)
        self.limit = self.mean * (1.0 - rel) - tol
        self.margin = self.mean - self.limit
        self.flat = self.test == "mean" or len(set(self.scores)) == 1
        self._thresholds: dict = {}

    def _check_alpha(self, alpha: float, replicates: int) -> None:
        if not 0.0 < alpha < 1.0:
            raise ValueError("alpha must be in (0, 1)")
        if self.test == "rank" and not self.flat:
            smallest = 1.0 / math.comb(self.n + replicates, replicates)
            if smallest > alpha:
                raise ValueError(
                    f"with {self.n} controls and {replicates} replicates, "
                    f"the smallest rank p-value is {smallest:.3g} > alpha "
                    f"{alpha}: add controls or replicates, or raise alpha"
                )

    def se(self, replicates: int) -> float:
        """Return the t test's standard error of a mean of `replicates`
        scores."""
        return self.sd * math.sqrt(1.0 / self.n + 1.0 / replicates)

    def threshold(
        self, rule: str, alpha: float, replicates: int
    ) -> float | None:
        """Return the least mean score that `rule` accepts at `alpha` for a
        candidate of `replicates` scores; None under the `rank` test.

        Raises
        ------
        ValueError
            If `rule` or `alpha` is out of range, or no candidate could pass
            the `rank` test at `alpha`.
        """
        key = rule, alpha, replicates
        if key not in self._thresholds:
            self._thresholds[key] = self._threshold(*key)
        return self._thresholds[key]

    def _threshold(
        self, rule: str, alpha: float, replicates: int
    ) -> float | None:
        if rule not in RULES:
            raise ValueError(f"rule must be one of {RULES}")
        self._check_alpha(alpha, replicates)
        if self.flat:
            return self.limit
        if self.test == "rank":
            return None
        q = t_quantile(1.0 - alpha, self.n - 1) * self.se(replicates)
        return self.limit - q if rule == "detectable_loss" else self.limit + q

    def accepts(self, scores: list, rule: str, alpha: float) -> bool:
        """Do one candidate's replicate `scores` pass `rule` at `alpha`?"""
        scores = [float(x) for x in scores]
        bound = self.threshold(rule, alpha, len(scores))
        if bound is not None:
            return fmean(scores) >= bound - 1e-12
        shifted = [x + self.margin for x in scores]
        if rule == "detectable_loss":
            return rank_pvalue(shifted, self.scores) > alpha
        return rank_pvalue(shifted, self.scores, upper=True) <= alpha

    def summary(self) -> dict:
        """Summarize the controls: `test`, `n`, `mean` and, with two or
        more, `sd`."""
        info = {"test": self.test, "n": self.n, "mean": self.mean}
        if self.sd is not None:
            info["sd"] = self.sd
        return info
