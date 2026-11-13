import math

from ._controls import Controls, chi2_quantile, t_quantile
from ._masks import ACCEPT, REJECT

SEQUENTIAL_RULES = ("sprt", "mixture")


class SequentialTest:
    """The sequential rules, which judge a candidate's scores one at a
    time against the wildtype controls and stop as soon as they decide.

    Like `noninferiority`, both rules accept only a candidate shown to lose
    less than the margin:

    * `sprt` is Wald's sequential probability ratio test of a loss of the
      whole margin against a loss smaller by the indifference zone,
      `indifference` of the margin. It accepts once the likelihood ratio
      reaches `1 / alpha`, and gives up, rejecting, once it falls to
      `futility`. Giving up does not show a loss beyond the margin.
    * `mixture` is the two-sided normal-mixture confidence sequence of
      Howard et al. (2021), tuned to the same indifference zone. It accepts
      once the whole interval for the candidate's mean is above the limit,
      and rejects once it is below.

    `error_rate` bounds the chance that any test of the whole search
    accepts a loss beyond the margin. An eighth of it goes to an upper
    confidence bound on the wildtype's mean, which raises the limit, and an
    eighth to one on its standard deviation, which every test takes as the
    noise. The rest is shared among the tests, as `alpha` gives. This
    assumes normal scores, with a candidate's no noisier than the
    controls'.

    If every control has the same score, there is no noise, and a
    candidate's first score decides: it is accepted if at least the limit.

    Parameters
    ----------
    kw : dict
        The assay's kwargs: `error_rate`, `indifference`, `futility`,
        `max_replicates`, `planned_tests` and `rel_tol`.
    controls : Controls
        The wildtype controls.
    n_sites : int
        The genome's size; `planned_tests` defaults to 8 times it.

    Raises
    ------
    ValueError
        If a kwarg is out of range, the controls vary but are not judged by
        `t`, or the margin is no wider than the bound on the wildtype's
        mean.
    """

    def __init__(self, kw: dict, controls: Controls, n_sites: int) -> None:
        self.error_rate = rate = float(kw.get("error_rate", 0.05))
        self.futility = float(kw.get("futility", 0.1))
        self.max_replicates = int(kw.get("max_replicates", 64))
        self.planned_tests = int(kw.get("planned_tests", 8 * n_sites))
        indifference = float(kw.get("indifference", 0.4))
        if not 0.0 < rate < 1.0:
            raise ValueError("error_rate must be in (0, 1)")
        if not 0.0 < self.futility < 1.0:
            raise ValueError("futility must be in (0, 1)")
        if not 0.0 < indifference <= 1.0:
            raise ValueError("indifference must be in (0, 1]")
        if self.max_replicates < 1 or self.planned_tests < 1:
            raise ValueError("max_replicates and planned_tests must be >= 1")
        self.mean, self.flat = controls.mean, controls.flat
        self.limit, self.sd_bound, self.gap = controls.limit, 0.0, 0.0
        if self.flat:
            return
        if controls.test != "t":
            raise ValueError("a sequential rule needs control_test 't'")
        n = controls.n
        bound = t_quantile(1.0 - rate / 8.0, n - 1) * controls.sd
        shift = bound / math.sqrt(n) * (1.0 - kw.get("rel_tol", 0.0))
        self.limit += shift
        self.sd_bound = controls.sd * math.sqrt(
            (n - 1) / chi2_quantile(rate / 8.0, n - 1)
        )
        room = self.mean - self.limit  # what a harmless deletion has in hand
        if room <= 0:
            raise ValueError(
                f"a sequential rule needs a margin above {shift:.3g}, the "
                "bound on the wildtype's mean: widen rel_tol or abs_tol, or "
                "add controls"
            )
        self.gap = indifference * room

    def alpha(self, index: int) -> float:
        """Return the alpha of the search's test number `index`, from 0.

        The first `planned_tests` tests share half the tests' three
        quarters of `error_rate` evenly, the next twice as many share a
        quarter, and so on: however many tests a search makes, their alphas
        sum to at most the tests' share.
        """
        epoch = (index // self.planned_tests + 1).bit_length() - 1
        share = 0.75 * self.error_rate / 2 ** (epoch + 1)
        return share / (self.planned_tests * 2**epoch)

    def _decide(
        self, scores: list, rule: str, alpha: float
    ) -> tuple[str | None, int]:
        """Judge `scores` in order, returning the first verdict reached, or
        None, and how many scores it took."""
        total = 0.0  # of the scores, less the limit
        log_accept, log_reject = -math.log(alpha), math.log(self.futility)
        rho = (self.sd_bound / self.gap) ** 2 if self.gap else 0.0
        for n, score in enumerate(scores, 1):
            total += float(score) - self.limit
            if self.flat:
                return (ACCEPT if total >= -1e-12 else REJECT), n
            if rule == "sprt":
                ratio = (
                    self.gap / self.sd_bound**2 * (total - n * self.gap / 2)
                )
                if ratio >= log_accept:
                    return ACCEPT, n
                if ratio <= log_reject:
                    return REJECT, n
            else:
                radius = self.sd_bound * math.sqrt(
                    (n + rho) * (math.log((n + rho) / rho) + 2.0 * log_accept)
                )
                if total >= radius:
                    return ACCEPT, n
                if total < -radius:
                    return REJECT, n
        return None, len(scores)

    def judge(self, scores: list, rule: str, alpha: float) -> str | None:
        """Judge one candidate's `scores`, in order, by `rule` at `alpha`.

        The verdict is the first one reached, so later scores never change
        it.

        Parameters
        ----------
        scores : list of float
            The candidate's scores so far.
        rule : str
            `sprt` or `mixture`.
        alpha : float
            The test's chance of accepting a loss beyond the margin.

        Returns
        -------
        str or None
            `ACCEPT`, `REJECT`, or None if the scores do not decide yet.
        """
        return self._decide(scores, rule, alpha)[0]

    def summary(self, rule: str) -> dict:
        """Summarize `rule`'s stage: its `limit`, `sd_bound`,
        `indifference` zone (in score units), `max_replicates` and
        `harmless_replicates`, how many scores at the controls' mean the
        search's first tests take to accept.

        Raises
        ------
        ValueError
            If such scores are not accepted within `max_replicates`.
        """
        harmless = [self.mean] * self.max_replicates
        verdict, n = self._decide(harmless, rule, self.alpha(0))
        if verdict != ACCEPT:
            raise ValueError(
                f"{rule} would not accept a deletion with no effect within "
                f"max_replicates {self.max_replicates}: raise it, widen "
                "rel_tol or abs_tol, or add controls"
            )
        return {
            "rule": rule,
            "limit": self.limit,
            "sd_bound": self.sd_bound,
            "indifference": self.gap,
            "max_replicates": self.max_replicates,
            "harmless_replicates": n,
        }
