import math
import random
import typing

from .._knockout._SequentialTest import SequentialTest
from .._knockout._controls import Controls
from ._find_maximal_subcritical_set_sort import (
    find_maximal_subcritical_set_sort,
)
from ._find_minimal_critical_sets_bisect import (
    find_minimal_critical_sets_bisect,
)

Wave = typing.Generator[list, list, typing.Any]


class StagedSearch:
    """Staged knockout skeletonization, for a genome with a cheap pass/fail
    screen for large failures and a long, scored trial for small ones.

    A search is a generator. It yields a wave, a list of requests, and is
    sent their answers in order, so that churn can replay it from recorded
    trials on every tick. A request is `("screen", tier, knockout)`,
    answered by whether the knockout fails that screen, or `("score",
    stage, knockout, index)`, answered by a score, or None if not viable.
    A knockout is the frozenset of sites deleted.

    After the wildtype controls, the search runs in two stages:

    1. `find_minimal_critical_sets_bisect`, the screens: the minimal sets
       of sites whose knockout fails, shrunk by bisection from random
       knockouts, and enough of each retained that none is wholly deleted.
    2. `find_maximal_subcritical_set_sort`, the ranking and confirmation:
       the rest sorted by their estimated cost, and the longest prefix
       whose knockout the controls' margin accepts.

    With `two_sided`, a gain counts as a loss does: the jackknife fails a
    knockout whose mean score is too far from the controls' either way,
    the ranking sorts the pool by the size of each site's effect, and a
    confirmation accepts only a knockout shown to be within the margin of
    the controls' mean above and below.

    Parameters
    ----------
    n_sites : int
        The genome's size.
    kw : dict
        The assay's kwargs; see docs/skeletonization.md.
    seed : int
        Seed of the search's own random number generator.
    num_control_trials : int
        How many times the wildtype is scored, as the controls.

    Raises
    ------
    ValueError
        If a kwarg is out of range.
    """

    policy = "staged"

    def __init__(
        self, n_sites: int, kw: dict, *, seed: int, num_control_trials: int
    ) -> None:
        screens = kw.get("screens", 1)
        self.n_screens = screens if isinstance(screens, int) else len(screens)
        self.batch_size = int(kw.get("batch_size", 20))
        self.max_set_size = int(kw.get("max_set_size", 6))
        self.jackknife_replicates = int(kw.get("jackknife_replicates", 4))
        self.reconfirm = kw.get("reconfirm")  # a second confirmation
        # how many first confirmations pass between second ones; 0, all
        self.reconfirm_every = (
            0
            if self.reconfirm is None
            else int(self.reconfirm.get("every", 1))
        )
        self.two_sided = bool(kw.get("two_sided", False))
        # looks a confirmation takes before its first, and a second one's
        self.early_looks = int(kw.get("early_looks", 0))
        self.reearly_looks = int(
            (self.reconfirm or {}).get("early_looks", self.early_looks)
        )
        self.max_ranking_trials = int(kw.get("max_ranking_trials", 3200))
        self.site_value = float(kw.get("site_value", 400))
        if min(self.n_screens, self.batch_size, self.max_set_size) < 1:
            raise ValueError(
                "screens, batch_size and max_set_size must be positive"
            )
        if self.jackknife_replicates < 1:
            raise ValueError("jackknife_replicates must be positive")
        if self.reconfirm_every < 0:
            raise ValueError("reconfirm's every must not be negative")
        if min(self.early_looks, self.reearly_looks) < 0:
            raise ValueError("early_looks must not be negative")
        self.sites = list(range(n_sites))
        self.kw = kw
        self.seed = seed
        self.rng = random.Random(seed)
        self.num_control_trials = num_control_trials
        self.phase = "start"
        self.usable = math.inf  # the loss the confirmation can accept
        # the sites the screens retain, as they find them, for progress
        self.tally: dict = {"critical": set(), "kept": set()}
        self.stats = {
            "screen_trials": [0] * self.n_screens,
            "jackknife_trials": 0,
            "ranking_trials": 0,
            "nonviable": 0,
        }

    def cost(self, loss: float) -> float:
        """Give what a loss of score counts for: itself or, if
        `two_sided`, its size, a gain counting as a loss does."""
        return abs(loss) if self.two_sided else loss

    def draw(self, pool: list[int], dose: float) -> frozenset[int]:
        """Draw a random knockout of `pool`, each site out with chance
        `dose`."""
        return frozenset(i for i in pool if self.rng.random() < dose)

    def run(self) -> Wave:
        """Run the search: the controls, the screens, the ranking and the
        confirmation.

        Returns
        -------
        Generator[list, list, dict]
            Yields waves and is sent their answers; returns the result:
            `retained`, `critical`, `redundant`, `adding_up`, `kept`,
            `released`, `certified`, `ranking`, `effects`, `error`,
            `predicted_cutoff`, `confirmations`, `reconfirm_every` (as
            the search left it) and `stats`.

        Raises
        ------
        ValueError
            If a wildtype control is not viable, or the `sprt` rule could
            not accept a harmless deletion.
        """
        self.phase = "controls"
        again = self.reconfirm or {}
        recontrols = int(again.get("num_control_trials", 0))
        if self.reconfirm is not None and recontrols < 2:
            raise ValueError("reconfirm needs 2 or more num_control_trials")
        scores = yield [
            ("score", "control", frozenset(), r)
            for r in range(self.num_control_trials)
        ] + [("score", "recontrol", frozenset(), r) for r in range(recontrols)]
        if None in scores:
            raise ValueError("a wildtype control was not viable")
        kw = {"planned_tests": 16, **self.kw}
        scores, rescores = (
            scores[: self.num_control_trials],
            scores[self.num_control_trials :],
        )
        self.controls = Controls(kw, scores)
        self.sequential = SequentialTest(kw, self.controls, len(self.sites))
        harmless = self.sequential.summary("sprt")["harmless_replicates"]
        self.first_look = int(kw.get("replicates", harmless))
        if self.reconfirm is not None:
            # the kwargs, less the first look's, under the reconfirmation's
            rekw = {k: v for k, v in kw.items() if k != "replicates"}
            rekw.update(again)
            self.recontrols = Controls(rekw, rescores)
            self.resequential = SequentialTest(
                rekw, self.recontrols, len(self.sites)
            )
            harmless = self.resequential.summary("sprt")["harmless_replicates"]
            self.refirst_look = int(rekw.get("replicates", harmless))
        # what the sprt can accept: its margin less half its zone
        self.usable = (
            self.controls.mean
            - self.sequential.limit
            - self.sequential.gap / 2.0
        )
        found = yield from find_minimal_critical_sets_bisect(self)
        pool = found.pop("pool")
        cut = yield from find_maximal_subcritical_set_sort(self, pool)
        return {
            "retained": frozenset(self.sites) - cut.pop("deleted"),
            **found,
            **cut,
            "stats": self.stats,
        }
