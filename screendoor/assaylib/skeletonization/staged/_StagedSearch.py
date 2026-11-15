import math
import random
import typing

from .._knockout._SequentialTest import SequentialTest
from .._knockout._controls import Controls
from .._knockout._masks import ACCEPT
from ._fit_effects import fit_effects

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

    The search assumes no rescue: a knockout that fails a screen fails it
    with more sites out, and one that passes does so with fewer. It runs
    in three stages:

    1. **Screens.** Random knockouts are screened at a dose that fails
       about half the time, and each failure is shrunk by bisection to a
       minimal failing set. A set of one is a critical site. A larger set
       is jackknifed: each member is put back in turn, and the rest
       tested with the next test up, the next screen or, after the last,
       long trials. If every such knockout is fine, the set is
       *redundant*, and one member is kept. If not, its losses *add up*,
       and each member that fails that test alone is critical. The dose
       rises as sites are retained, until the whole remaining pool passes
       when knocked out together. Each later screen then searches the
       pool by halving.
    2. **Ranking.** Score random knockouts of the pool with long trials and
       estimate each site's cost by least squares, doubling the trials
       until another deleted site would cost over `site_value` of them.
    3. **Confirmation.** Sort the pool from least to most costly and find,
       by bisection, the longest prefix whose knockout the `sprt` rule
       accepts against the wildtype controls. With `reconfirm`, a knockout
       that is accepted must pass the rule a second time, on the scores
       of a costlier trial against controls of its own; that test comes
       after every `every` acceptances, and at the end.

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
        self.sites = list(range(n_sites))
        self.kw = kw
        self.seed = seed
        self.rng = random.Random(seed)
        self.num_control_trials = num_control_trials
        self.critical: set = set()  # sites that fail a test alone
        self.kept: set = set()  # one member of each redundant set
        self.redundant: list = []  # (tier, redundant set)
        self.adding_up: list = []  # (tier, failing set whose losses add)
        self.released: list = []  # members kept, then found needless
        # what each screen's trials have shown, to answer what they imply
        self.lethal: list = [[] for _ in range(self.n_screens)]
        self.passing: list = [[] for _ in range(self.n_screens)]
        self.screened: list = [{} for _ in range(self.n_screens)]
        self.scored: dict = {}  # whether each jackknifed knockout fails
        self.phase = "start"
        self.dose = 0.0
        self.usable = math.inf  # the loss the confirmation can accept
        self.certified = False
        self.confirmations: list = []
        self.stats = {
            "screen_trials": [0] * self.n_screens,
            "jackknife_trials": 0,
            "ranking_trials": 0,
            "nonviable": 0,
        }

    def pool(self) -> list[int]:
        """List the sites neither critical nor kept."""
        return sorted(set(self.sites) - self.critical - self.kept)

    def known(self, deleted: frozenset[int], tier: int) -> bool | None:
        """Tell whether a knockout fails a screen, if its trials so far
        settle that: it fails if it contains a failing set, and passes if
        a knockout containing it passed."""
        if not deleted:
            return False  # the wildtype
        if deleted in self.screened[tier]:
            return self.screened[tier][deleted]
        if any(s <= deleted for s in self.lethal[tier]):
            return True
        if any(deleted <= p for p in self.passing[tier]):
            return False
        return None

    def ask(self, requests: list[tuple]) -> Wave:
        """Get the answers to requests, asking only for the screen trials
        that earlier ones do not settle.

        Parameters
        ----------
        requests : list of tuple
            Requests, as a wave has them.

        Returns
        -------
        Generator[list, list, list]
            Yields waves and is sent their answers; returns each request's
            answer.
        """
        answers, wave = {}, []
        for request in dict.fromkeys(requests):
            if request[0] == "screen":
                answers[request] = self.known(request[2], request[1])
            if answers.get(request) is None:
                wave.append(request)
        for request, answer in zip(wave, (yield wave) if wave else ()):
            answers[request] = answer
            if request[0] != "screen":
                self.stats["jackknife_trials"] += request[1] == "jackknife"
                continue
            _, tier, deleted = request
            self.stats["screen_trials"][tier] += 1
            self.screened[tier][deleted] = answer
            if answer and len(deleted) == 1:
                self.lethal[tier].append(deleted)
            elif not answer:
                self.passing[tier] = [
                    p for p in self.passing[tier] if not p <= deleted
                ]
                self.passing[tier].append(deleted)
        return [answers[request] for request in requests]

    def screen(self, knockouts: list[frozenset[int]], tier: int) -> Wave:
        """Get whether each knockout fails a screen.

        Returns
        -------
        Generator[list, list, list of bool]
            Yields waves and is sent their answers; returns whether each
            knockout fails.
        """
        return (yield from self.ask([("screen", tier, k) for k in knockouts]))

    def together(self, searches: list[typing.Generator]) -> Wave:
        """Advance several searches side by side, each wave taking the
        next requests of every one.

        Parameters
        ----------
        searches : list of Generator
            Searches that yield a list of requests at a time and are sent
            their answers, as `shrink`, `settle` and `jackknife` are.

        Returns
        -------
        Generator[list, list, list]
            Yields waves and is sent their answers; returns what each
            search returned.
        """
        results: list = [None] * len(searches)
        asking = {}

        def advance(i: int, answers: list | None) -> None:
            try:
                asking[i] = searches[i].send(answers)
            except StopIteration as stop:
                results[i] = stop.value
                asking.pop(i, None)

        for i in range(len(searches)):
            advance(i, None)
        while asking:
            order = [(i, len(asking[i])) for i in asking]
            answers = yield from self.ask(
                [request for i, _ in order for request in asking[i]]
            )
            for i, count in order:
                advance(i, answers[:count])
                answers = answers[count:]
        return results

    def shrink(
        self, failing: frozenset[int], tier: int
    ) -> typing.Generator[list, list, frozenset | None]:
        """Shrink a failing knockout to a minimal failing set, by bisection
        for each member in turn.

        Parameters
        ----------
        failing : frozenset of int
            A knockout that fails the screen.
        tier : int
            The screen.

        Returns
        -------
        Generator[list, list, frozenset or None]
            Yields a request at a time and is sent its answer; returns a
            minimal failing set, or None past `max_set_size` members.
        """

        def fails(deleted: list[int]) -> typing.Generator[list, list, bool]:
            return (yield [("screen", tier, frozenset(deleted))])[0]

        required, candidates = [], sorted(failing)
        while not (required and (yield from fails(required))):
            if not candidates or len(required) >= self.max_set_size:
                return None
            lo, hi = 1, len(candidates)  # the prefix of length hi fails
            while lo < hi:
                mid = (lo + hi) // 2
                if (yield from fails(required + candidates[:mid])):
                    hi = mid
                else:
                    lo = mid + 1
            required.append(candidates[lo - 1])
            candidates = candidates[: lo - 1]
        return frozenset(required)

    def test(
        self, knockouts: list[frozenset[int]], level: int
    ) -> typing.Generator[list, list, list[bool]]:
        """Get whether each knockout fails the test at `level`: that
        screen or, past the last screen, long trials, which a knockout
        fails if its mean loss over `jackknife_replicates` of them is more
        than the confirmation could accept.

        Returns
        -------
        Generator[list, list, list of bool]
            Yields its requests once and is sent their answers; returns
            whether each knockout fails.
        """
        if level < self.n_screens:
            return (yield [("screen", level, k) for k in knockouts])
        reps = self.jackknife_replicates
        new = [k for k in dict.fromkeys(knockouts) if k not in self.scored]
        if new:
            scores = yield [
                ("score", "jackknife", k, r) for k in new for r in range(reps)
            ]
            for j, deleted in enumerate(new):
                mine = scores[j * reps : (j + 1) * reps]
                self.scored[deleted] = (
                    None in mine
                    or self.controls.mean - sum(mine) / reps > self.usable
                )
        return [self.scored[deleted] for deleted in knockouts]

    def jackknife(
        self, found: frozenset[int], tier: int
    ) -> typing.Generator[list, list, bool]:
        """Tell a redundant set from losses adding up, by putting each
        member of a minimal failing set back in turn.

        The knockouts that leave one member in are tested with the next
        test up, two of them first. If none fails, the set is redundant:
        harmless until all of it is out. One member is then kept. If one
        fails, the set's losses add up, and each member that fails that
        test when knocked out alone is critical. Where losses add up, one
        of any two such knockouts keeps at least half the set's loss, so
        the first two settle it.

        Parameters
        ----------
        found : frozenset of int
            A minimal failing set of the screen.
        tier : int
            The screen.

        Returns
        -------
        Generator[list, list, bool]
            Yields its requests and is sent their answers; returns whether
            a site was newly retained.
        """
        if found not in self.lethal[tier]:
            self.lethal[tier].append(found)
        before = len(self.critical) + len(self.kept)
        members = sorted(found)
        if len(found) == 1:
            self.critical |= found
        elif all(
            found != known for _, known in self.redundant + self.adding_up
        ):
            outs = [found - {i} for i in members]
            fails = yield from self.test(outs[:2], tier + 1)
            if not any(fails):
                fails = yield from self.test(outs[2:], tier + 1)
            if not any(fails):
                self.redundant.append((tier, found))
                self.kept.add(min(found))
            else:
                self.adding_up.append((tier, found))
                singles = [frozenset([i]) for i in members]
                alone = yield from self.test(singles, tier + 1)
                self.critical |= {i for i, f in zip(members, alone) if f}
        return len(self.critical) + len(self.kept) > before

    def settle(
        self, sites: typing.Iterable[int], tier: int
    ) -> typing.Generator[list, list, None]:
        """Shrink failing sets out of a block of sites until what is left
        of it passes, or its failures retain no site.

        Returns
        -------
        Generator[list, list, None]
            Yields its requests and is sent their answers.
        """
        while True:
            deleted = frozenset(sites) - self.critical - self.kept
            if not deleted or not (yield [("screen", tier, deleted)])[0]:
                return
            found = yield from self.shrink(deleted, tier)
            if found is None or not (yield from self.jackknife(found, tier)):
                return

    def draw(self, pool: list[int], dose: float) -> frozenset[int]:
        """Draw a random knockout of `pool`, each site out with chance
        `dose`."""
        return frozenset(i for i in pool if self.rng.random() < dose)

    def ramp(self) -> Wave:
        """Find the first screen's critical sites and redundant sets by
        random knockouts at the dose that fails about half the time.

        A failure with no failing set of `max_set_size` sites or fewer is
        searched by halving with the next screen, if there is one, for
        sites harmful alone. The ramp ends when the whole pool passes, or
        when three rounds in a row, or one at a full dose, retain no site:
        what still fails is small losses adding up.

        Returns
        -------
        Generator[list, list, None]
            Yields waves and is sent their answers.
        """
        self.dose = min(0.5, 2.0 / max(1, len(self.sites)))
        idle = 0  # rounds in a row whose failures retained nothing
        while True:
            self.phase = "ramp"
            pool = self.pool()
            draws = [
                self.draw(pool, self.dose)
                for _ in range(self.batch_size if self.dose < 1.0 else 0)
            ]
            fails = yield from self.screen([frozenset(pool), *draws], 0)
            if not fails[0]:
                return  # the checkpoint: the whole pool passes
            if draws:
                failing = [d for d, f in zip(draws, fails[1:]) if f]
                rate = len(failing) / len(draws)
                failing = list(dict.fromkeys(failing))
            else:  # at a full dose, the one knockout is the whole pool
                failing, rate = [frozenset(pool)], 1.0
            before = len(self.critical) + len(self.kept)
            self.phase = "shrink"
            shrunk = yield from self.together(
                [self.shrink(deleted, 0) for deleted in failing]
            )
            self.phase = "jackknife"
            yield from self.together(
                [
                    self.jackknife(found, 0)
                    for found in dict.fromkeys(shrunk)
                    if found is not None
                ]
            )
            for deleted, found in zip(failing, shrunk):
                rest = deleted - self.critical - self.kept
                if found is not None or self.n_screens < 2:
                    continue
                if (yield from self.screen([rest], 0))[0]:
                    self.phase = "bump"
                    yield from self.halve(sorted(rest), 1)
            progress = len(self.critical) + len(self.kept) > before
            idle = 0 if progress or not failing else idle + 1
            if idle >= 3 or (idle and not draws):
                return
            self.dose = min(1.0, self.dose * 4.0 ** (0.5 - rate))

    def halve(self, sites: list[int], tier: int) -> Wave:
        """Find a screen's critical sites and redundant sets among `sites`
        by halving.

        Going down, each failing block is halved and both halves screened,
        a level at a time; a failing single site is critical, and blocks
        dense with failures are screened site by site. Coming back up,
        each failing block is settled, which finds the sets that straddle
        its halves. Small blocks cannot fail by small losses adding up,
        so those do not hide a site that is harmful alone.

        Returns
        -------
        Generator[list, list, None]
            Yields waves and is sent their answers.
        """
        order = list(sites)
        self.rng.shuffle(order)
        if (
            not order
            or not (yield from self.screen([frozenset(order)], tier))[0]
        ):
            return
        levels, frontier = [[order]], [order]
        while frontier:
            halves = []
            for block in frontier:
                halves += [block[: len(block) // 2], block[len(block) // 2 :]]
            fails = yield from self.screen(list(map(frozenset, halves)), tier)
            failing = [h for h, f in zip(halves, fails) if f]
            share = min(len(failing) / len(halves), 1 - 0.5 / len(halves))
            self.critical.update(h[0] for h in failing if len(h) == 1)
            failing = [h for h in failing if len(h) > 1]
            levels.append(failing)
            size = max(map(len, halves))
            if failing and (size <= 4 or 1 - (1 - share) ** (1 / size) >= 0.2):
                singles = [i for half in failing for i in half]
                fails = yield from self.screen(
                    [frozenset([i]) for i in singles], tier
                )
                self.critical.update(i for i, f in zip(singles, fails) if f)
                failing = []
            frontier = failing
        for level in reversed(levels):  # a level's blocks are disjoint
            yield from self.together(
                [self.settle(block, tier) for block in level]
            )

    def release(self) -> bool:
        """Stop keeping any member of a redundant set that has another
        member retained anyway, as a critical site or for another set.
        Returns whether any was released."""
        freed = []
        for site in sorted(self.kept):
            retained = self.critical | (self.kept - {site})
            if all(s & retained for _, s in self.redundant if site in s):
                self.kept.discard(site)
                freed.append(site)
        self.released += freed
        return bool(freed)

    def learn(self) -> Wave:
        """Run the screens: find the critical sites and redundant sets,
        and so the pool of sites left to rank.

        Returns
        -------
        Generator[list, list, None]
            Yields waves and is sent their answers.
        """
        yield from self.ramp()
        while True:
            self.phase = "certify"
            yield from self.together([self.settle(self.pool(), 0)])
            for tier in range(1, self.n_screens):
                self.phase = "sweep"
                yield from self.halve(self.pool(), tier)
            if not self.release():
                break
        whole = frozenset(self.pool())
        self.certified = not (yield from self.screen([whole], 0))[0]

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
        costly = min(sites, max(1, round(load / typical)))
        costs = [load / costly] * costly + [0.0] * (sites - costly)

        def deleted(noise: list[float], spread: float) -> int:
            total, count = 0.0, 0
            ranked = sorted(
                zip(costs, noise), key=lambda c: c[0] + spread * c[1]
            )
            for cost, _ in ranked:
                total += cost
                if total > self.usable:
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
        `site_value` trials.

        Returns
        -------
        Generator[list, list, tuple]
            Yields waves and is sent their answers; returns the pool from
            least to most costly, each site's estimated cost, their
            standard error, and how many sites the estimates predict can
            be deleted.
        """
        usable = self.usable
        knockouts, losses, asked, dose = [], [], 0, 0.5
        effects, error = dict.fromkeys(pool, 0.0), math.inf
        target = min(100, self.max_ranking_trials)
        live = list(pool)  # the sites still worth knocking out
        while len(live) > 1 and asked < target:
            batch = [self.draw(live, dose) for _ in range(target - asked)]
            scores = yield [
                ("score", "rank", deleted, asked + k)
                for k, deleted in enumerate(batch)
            ]
            asked = target
            for deleted, score in zip(batch, scores):
                if score is None:
                    self.stats["nonviable"] += 1
                else:
                    knockouts.append(deleted)
                    losses.append(self.controls.mean - score)
            effects, error = fit_effects(knockouts, losses, pool)
            # a site that clearly costs more than can be accepted will
            # not be deleted: leave it in from here on
            live = [i for i in live if effects[i] - 2.0 * error <= usable]
            load = sum(effects[i] for i in live)
            dose = min(0.5, max(0.1, usable / load)) if load > 0 else 0.5
            target = min(2 * asked, self.max_ranking_trials)
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
                    random.Random(f"{self.seed}:gain:{asked}"),
                )
                for shift in (-doubt, 0.0, doubt)
            )
            if gain * self.site_value < asked:
                break
        self.stats["ranking_trials"] = asked
        order = sorted(pool, key=lambda i: (effects[i], i))
        total, cutoff = 0.0, 0
        for site in order:  # less a standard error: noise is not a cost
            total += max(0.0, effects[site] - error)
            if total > usable:
                break
            cutoff += 1
        return order, effects, error, cutoff

    def stream(self, deleted: frozenset[int], stage: str = "confirm") -> Wave:
        """Judge a knockout's `stage` scores by the `sprt` rule, look by
        look, from the first look's scores and doubling up to
        `max_replicates`: its `confirm` scores against the controls, or
        its `reconfirm` scores, of the costlier trial, against that
        trial's own.

        Returns
        -------
        Generator[list, list, bool]
            Yields waves and is sent their answers; returns whether the
            knockout is accepted.
        """
        again = stage == "reconfirm"
        test = self.resequential if again else self.sequential
        first = self.refirst_look if again else self.first_look
        alpha = test.alpha(len(self.confirmations))
        total, verdict = min(first, test.max_replicates), None
        while True:
            scores = yield [("score", stage, deleted, r) for r in range(total)]
            if None not in scores:
                verdict = test.judge(scores, "sprt", alpha)
            if None in scores or verdict or total >= test.max_replicates:
                break
            total = min(2 * total, test.max_replicates)
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
        lo, hi = 0, len(order) + 1  # the prefix lo passes, hi fails
        sure, unsure = 0, 0  # the prefix reconfirmed; acceptances since
        adaptive = (self.reconfirm or {}).get("adaptive")
        probe = min(max(cutoff, 1), len(order))
        while True:
            every = self.reconfirm_every
            while hi - lo > 1 and not (every and unsure >= every):
                if (yield from self.stream(frozenset(order[:probe]))):
                    lo, unsure = probe, unsure + 1
                else:
                    hi = probe
                probe = (lo + hi) // 2
            if self.reconfirm is None or lo == sure:
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
        yield from self.learn()
        self.phase = "rank"
        order, effects, error, cutoff = yield from self.rank(self.pool())
        self.phase = "confirm"
        deleted = yield from self.confirm(order, cutoff)
        return {
            "retained": frozenset(self.sites) - deleted,
            "critical": sorted(self.critical),
            "redundant": [(tier, sorted(s)) for tier, s in self.redundant],
            "adding_up": [(tier, sorted(s)) for tier, s in self.adding_up],
            "kept": sorted(self.kept),
            "released": sorted(self.released),
            "certified": self.certified,
            "ranking": order,
            "effects": [effects[i] for i in order],
            "error": error,
            "predicted_cutoff": cutoff,
            "confirmations": self.confirmations,
            "reconfirm_every": self.reconfirm_every,
            "stats": self.stats,
        }
