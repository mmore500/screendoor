"""Judging a genotype's score against the wildtype's control trials.

The wildtype runs ``num_control_trials`` times: the trial script measures it
against itself (a wildtype-vs-wildtype competition, or a Test CPU score
less the wildtype's, ...). Those scores are the null distribution a
candidate's scores are judged against, by one of ``CONTROL_TESTS``:

* ``mean``: accept if the candidates' mean is at least the controls' mean
  less the tolerance (``rel_tol``, ``abs_tol``). The default with one
  control.
* ``t``: the default with two or more controls. A one-sided t prediction
  bound: reject if the candidates' mean is
  below the tolerance limit by more than ``t(1 - alpha, n - 1) * s *
  sqrt(1/n + 1/r)``, with ``n`` controls of standard deviation ``s`` and
  ``r`` replicates. It assumes a candidate's noise is the controls'.
* ``rank``: a one-sided exact Mann-Whitney (Wilcoxon rank-sum) test of the
  replicates, shifted up by the tolerance, against the controls. Reject if
  p <= alpha. Ties count in the candidate's favour. It assumes nothing
  about the distribution's shape.

If every control scores the same, ``t`` and ``mean`` reject any lower
score, as does ``rank`` (the smallest p-value must be at most alpha).
"""

import math
from statistics import fmean, stdev

CONTROL_TESTS = ("mean", "t", "rank")


def _betacf(a: float, b: float, x: float) -> float:
    """The continued fraction of the incomplete beta function (Lentz)."""
    tiny = 1e-300

    def clamp(v):
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
    """The regularized incomplete beta function I_x(a, b)."""
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
    """Student's t distribution function."""
    tail = 0.5 * _betainc(df / 2.0, 0.5, df / (df + t * t))
    return 1.0 - tail if t > 0 else tail


def t_quantile(p: float, df: float) -> float:
    """Student's t quantile, by bisection on ``t_cdf``."""
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


def _rank_sum_counts(r: int, n: int) -> list:
    """How many orderings of ``r`` candidates among ``n`` controls give
    each U (the pairs in which the candidate is the larger), U = 0..r*n."""
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


def rank_pvalue(scores, controls, *, upper: bool = False) -> float:
    """One-sided exact Mann-Whitney p-value that ``scores`` come from a
    distribution below the ``controls``' (or, with ``upper``, above it).
    Ties count against the alternative."""
    counts = _rank_sum_counts(len(scores), len(controls))
    if upper:
        u = sum(c < x for x in scores for c in controls)
        return sum(counts[u:]) / sum(counts)
    u = sum(c <= x for x in scores for c in controls)
    return sum(counts[: u + 1]) / sum(counts)


RULES = ("detectable_loss", "noninferiority")


class Controls:
    """The wildtype controls' scores, and the rules that judge a
    candidate's replicate scores against them.

    ``limit`` is the controls' mean less the tolerance, ``mean * (1 -
    rel_tol) - abs_tol``, and ``margin`` is how far below the mean it is.
    Each rule has a one-sided ``alpha``:

    * ``detectable_loss`` rejects only a candidate whose scores are
      significantly below ``limit``.
    * ``noninferiority`` accepts only a candidate whose scores are
      significantly above ``limit``: shown to lose less than ``margin``.

    If every control has the same score, there is no noise to test
    against, and every rule accepts just the candidates whose mean is at
    least ``limit``.
    """

    def __init__(self, kw: dict, scores: list):
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
        """The t test's standard error for a mean of ``replicates``."""
        return self.sd * math.sqrt(1.0 / self.n + 1.0 / replicates)

    def threshold(self, rule: str, alpha: float, replicates: int):
        """The least mean score accepted, or None for ``rank``."""
        key = rule, alpha, replicates
        if key not in self._thresholds:
            self._thresholds[key] = self._threshold(*key)
        return self._thresholds[key]

    def _threshold(self, rule: str, alpha: float, replicates: int):
        if rule not in RULES:
            raise ValueError(f"rule must be one of {RULES}")
        self._check_alpha(alpha, replicates)
        if self.flat:
            return self.limit
        if self.test == "rank":
            return None
        q = t_quantile(1.0 - alpha, self.n - 1) * self.se(replicates)
        return self.limit - q if rule == "detectable_loss" else self.limit + q

    def accepts(self, scores, rule: str, alpha: float) -> bool:
        """Whether ``scores`` (one candidate's replicates) pass ``rule``."""
        scores = [float(x) for x in scores]
        bound = self.threshold(rule, alpha, len(scores))
        if bound is not None:
            return fmean(scores) >= bound - 1e-12
        shifted = [x + self.margin for x in scores]
        if rule == "detectable_loss":
            return rank_pvalue(shifted, self.scores) > alpha
        return rank_pvalue(shifted, self.scores, upper=True) <= alpha

    def summary(self) -> dict:
        info = {"test": self.test, "n": self.n, "mean": self.mean}
        if self.sd is not None:
            info["sd"] = self.sd
        return info


def control_judge(kw: dict, controls: list, replicates: int):
    """A function from a candidate's replicate scores to accept (True) or
    reject by the ``detectable_loss`` rule at ``alpha``, and a summary of the
    controls and the rule."""
    c = Controls(kw, controls)
    alpha = float(kw.get("alpha", 0.05))
    threshold = c.threshold("detectable_loss", alpha, replicates)
    info = c.summary()
    if c.test != "mean":
        info["alpha"] = alpha
    if threshold is None:
        info["smallest_pvalue"] = 1.0 / math.comb(c.n + replicates, replicates)
    else:
        info["threshold"] = threshold

    def judge(scores) -> bool:
        return c.accepts(scores, "detectable_loss", alpha)

    return judge, info
