import math
import random
import typing

from .._knockout._SequentialTest import SequentialTest
from .._knockout._masks import ACCEPT, REJECT
from ._fit_effects import fit_effects

Wave = typing.Generator[list, list, typing.Any]


class _SubcriticalSetSearch:
    """A staged search's ranking and confirmation, and the confirmations
    they have made.

    Parameters
    ----------
    search : StagedSearch
        The search, with its controls set, for its settings, controls and
        random number generator.
    """

    def __init__(self, search: typing.Any) -> None:
        self.search = search
        self.confirmations: list = []
        # how many first confirmations pass between second ones; 0, all
        self.reconfirm_every = search.reconfirm_every

    def expected_gain(
        self,
        sites: int,
        load: float,
        error: float,
        typical: float,
        rng: random.Random,
    ) -> float:
        """Predict how many more sites halving the costs' variance would
        delete, if a share of the sites each cost `typical` and the rest
        nothing."""
        usable = self.search.usable
        costly = min(sites, max(1, round(load / typical)))
        costs = [load / costly] * costly + [0.0] * (sites - costly)

        def deleted(noise: list[float], spread: float) -> int:
            total, count = 0.0, 0
            ranked = sorted(
                zip(costs, noise), key=lambda c: c[0] + spread * c[1]
            )
            for cost, _ in ranked:
                total += cost
                if total > usable:
                    break
                count += 1
            return count

        gain = 0
        for _ in range(50):  # the same noise for both, to compare them
            noise = [rng.gauss(0.0, 1.0) for _ in costs]
            gain += deleted(noise, error / math.sqrt(2.0))
            gain -= deleted(noise, error)
        return gain / 50

    def rank(self, pool: list[int]) -> Wave:
        """Estimate the cost of each site of `pool` from the scores of
        random knockouts, and sort the pool by it.

        The knockouts' dose is that at which about half lose `usable`, the
        loss the confirmation can accept, and at most 50%. A site whose
        cost is clearly over `usable` alone is left in from then on. The
        trials double from 100 until `max_ranking_trials`, or until, with
        four trials a site or more, the remaining sites' cost is within
        half of `usable` or another deleted site would cost over
        `site_value` trials. If `two_sided`, a site's cost is the size of
        its effect, less a standard error, and the pool is sorted by that
        size; the sites' effects still add up with their signs.

        Returns
        -------
        Generator[list, list, tuple]
            Yields waves and is sent their answers; returns the pool from
            least to most costly, each site's estimated cost, their
            standard error, and how many sites the estimates predict can
            be deleted.
        """
        search = self.search
        cost, usable = search.cost, search.usable
        knockouts, losses, asked, dose = [], [], 0, 0.5
        effects, error = dict.fromkeys(pool, 0.0), math.inf
        target = min(100, search.max_ranking_trials)
        live = list(pool)  # the sites still worth knocking out
        while len(live) > 1 and asked < target:
            batch = [search.draw(live, dose) for _ in range(target - asked)]
            scores = yield [
                ("score", "rank", deleted, asked + k)
                for k, deleted in enumerate(batch)
            ]
            asked = target
            for deleted, score in zip(batch, scores):
                if score is None:
                    search.stats["nonviable"] += 1
                else:
                    knockouts.append(deleted)
                    losses.append(search.controls.mean - score)
            effects, error = fit_effects(knockouts, losses, pool)
            # a site that clearly costs more than can be accepted will
            # not be deleted: leave it in from here on
            live = [
                i for i in live if cost(effects[i]) - 2.0 * error <= usable
            ]
            load = sum(
                (
                    max(0.0, abs(effects[i]) - error)
                    if search.two_sided
                    else effects[i]
                )
                for i in live
            )
            dose = min(0.5, max(0.1, usable / load)) if load > 0 else 0.5
            target = min(2 * asked, search.max_ranking_trials)
            if asked < 4 * len(pool) or math.isinf(error) or not live:
                continue
            mean = load / len(live)
            if load <= usable / 2 or mean <= 0:
                break  # it all fits: there is nothing to rank
            # the typical size of a cost: their mean square over their
            # mean, less the noise's share, give or take what is in doubt
            squared = sum(effects[i] ** 2 for i in live) / len(live)
            squared -= error * error
            doubt = 2.0 * math.sqrt(2.0 / len(live)) * error * error
            gain = max(
                self.expected_gain(
                    len(live),
                    load,
                    error,
                    max(mean, (squared + shift) / mean),
                    random.Random(f"{search.seed}:gain:{asked}"),
                )
                for shift in (-doubt, 0.0, doubt)
            )
            if gain * search.site_value < asked:
                break
        search.stats["ranking_trials"] = asked
        order = sorted(pool, key=lambda i: (cost(effects[i]), i))
        total, cutoff = 0.0, 0
        for site in order:  # less a standard error: noise is not a cost
            sure = max(0.0, cost(effects[site]) - error)
            total += math.copysign(sure, effects[site])
            if cost(total) > usable:
                break
            cutoff += 1
        return order, effects, error, cutoff

    def judge(
        self, test: SequentialTest, scores: list, alpha: float
    ) -> str | None:
        """Judge scores by the `sprt` rule and, if `two_sided`, their
        mirror image about the controls' mean too, where a gain shows as
        a loss: accepted if both are, and rejected if either is."""
        verdicts = {test.judge(scores, "sprt", alpha)}
        if self.search.two_sided:
            mirror = [2.0 * test.mean - score for score in scores]
            verdicts.add(test.judge(mirror, "sprt", alpha))
        if REJECT in verdicts:
            return REJECT
        return ACCEPT if verdicts == {ACCEPT} else None

    def stream(self, deleted: frozenset[int], stage: str = "confirm") -> Wave:
        """Judge a knockout's `stage` scores by the `sprt` rule, look by
        look, from the first look's scores and doubling up to
        `max_replicates`: its `confirm` scores against the controls, or
        its `reconfirm` scores, of the costlier trial, against that
        trial's own. With `early_looks`, as many looks come before the
        first, each of half the scores of the next, so that a knockout
        far from the limit is judged on few.

        Returns
        -------
        Generator[list, list, bool]
            Yields waves and is sent their answers; returns whether the
            knockout is accepted.
        """
        search, again = self.search, stage == "reconfirm"
        test = search.resequential if again else search.sequential
        first = search.refirst_look if again else search.first_look
        alpha = test.alpha(len(self.confirmations))
        look, verdict = (
            -(search.reearly_looks if again else search.early_looks),
            None,
        )
        while True:
            total = min(math.ceil(first * 2.0**look), test.max_replicates)
            scores = yield [("score", stage, deleted, r) for r in range(total)]
            if None not in scores:
                verdict = self.judge(test, scores, alpha)
            if None in scores or verdict or total >= test.max_replicates:
                break
            look += 1
        counted = "reconfirm_replicates" if again else "replicates"
        self.confirmations.append(
            {
                "deleted": len(deleted),
                counted: total,
                "accepted": verdict == ACCEPT,
            }
        )
        return verdict == ACCEPT

    def confirm(self, order: list[int], cutoff: int) -> Wave:
        """Find the longest prefix of `order` whose knockout is accepted,
        by bisection from the predicted `cutoff`.

        With `reconfirm`, the bisection is by the first confirmation, and
        the costlier one judges the longest prefix accepted so far after
        every `every` that the first accepts, and where the bisection
        ends. A prefix it rejects becomes the bisection's upper bound,
        over the longest it has accepted. If `adaptive`, each prefix it
        accepts doubles `every`, and each it rejects halves it.

        Returns
        -------
        Generator[list, list, frozenset of int]
            Yields waves and is sent their answers; returns the sites to
            delete.
        """
        reconfirm = self.search.reconfirm
        lo, hi = 0, len(order) + 1  # the prefix lo passes, hi fails
        sure, unsure = 0, 0  # the prefix reconfirmed; acceptances since
        adaptive = (reconfirm or {}).get("adaptive")
        probe = min(max(cutoff, 1), len(order))
        while True:
            every = self.reconfirm_every
            while hi - lo > 1 and not (every and unsure >= every):
                if (yield from self.stream(frozenset(order[:probe]))):
                    lo, unsure = probe, unsure + 1
                else:
                    hi = probe
                probe = (lo + hi) // 2
            if reconfirm is None or lo == sure:
                return frozenset(order[:lo])
            prefix = frozenset(order[:lo])
            if (yield from self.stream(prefix, "reconfirm")):
                sure = lo
                self.reconfirm_every *= 2 if adaptive else 1
            else:  # backtrack, below the prefix it rejected
                lo, hi = sure, lo
                if adaptive:
                    self.reconfirm_every = max(1, every // 2)
            unsure, probe = 0, (lo + hi) // 2

    def run(self, pool: list[int]) -> Wave:
        """Rank the pool, then confirm the cut.

        Returns
        -------
        Generator[list, list, dict]
            Yields waves and is sent their answers; returns the result, as
            `find_maximal_subcritical_set_sort` does.
        """
        self.search.phase = "rank"
        order, effects, error, cutoff = yield from self.rank(pool)
        self.search.phase = "confirm"
        deleted = yield from self.confirm(order, cutoff)
        return {
            "deleted": deleted,
            "ranking": order,
            "effects": [effects[i] for i in order],
            "error": error,
            "predicted_cutoff": cutoff,
            "confirmations": self.confirmations,
            "reconfirm_every": self.reconfirm_every,
        }


def find_maximal_subcritical_set_sort(
    search: typing.Any, pool: list[int]
) -> Wave:
    """Find, by a staged search's long trials, the longest run of a pool's
    sites, sorted by cost, whose knockout the controls' margin accepts.

    A subcritical set is one whose knockout costs less than would fail
    the confirmation. Random knockouts of the pool are scored with long
    trials, and each site's cost estimated by least squares, the trials
    doubling until another deleted site would cost over `site_value` of
    them. The pool is sorted from least to most costly, and the longest
    prefix whose knockout the `sprt` rule accepts against the wildtype
    controls is found by bisection, from the prefix the estimates predict.
    With `reconfirm`, a knockout that is accepted must pass the rule a
    second time, on the scores of a costlier trial against controls of
    its own; that test comes after every `every` acceptances, and at the
    end.

    The prefix is maximal along the sort, not over every set: the sort
    assumes the sites' costs add up.

    Parameters
    ----------
    search : StagedSearch
        The search, with its controls set, for its settings, controls and
        random number generator.
    pool : list of int
        The sites to rank and delete from, as the screens leave them.

    Returns
    -------
    Generator[list, list, dict]
        Yields waves and is sent their answers; returns the sites
        `deleted`, the `ranking` of the pool, the `effects` estimated in
        its order and their standard `error`, the `predicted_cutoff`, the
        `confirmations` made, and `reconfirm_every` as the search left it.
    """
    return (yield from _SubcriticalSetSearch(search).run(pool))
