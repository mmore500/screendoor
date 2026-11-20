import typing

Wave = typing.Generator[list, list, typing.Any]


class _CriticalSetSearch:
    """What a staged search's screens have shown: the sites retained so
    far, and each screen's trials, to answer what they imply.

    Parameters
    ----------
    search : StagedSearch
        The search, for its settings, controls, random number generator
        and tallies.
    """

    def __init__(self, search: typing.Any) -> None:
        self.search = search
        n_screens = search.n_screens
        self.critical: set = set()  # sites that fail a test alone
        self.kept: set = set()  # one member of each redundant set
        self.redundant: list = []  # (tier, redundant set)
        self.adding_up: list = []  # (tier, failing set whose losses add)
        self.released: list = []  # members kept, then found needless
        # what each screen's trials have shown, to answer what they imply
        self.failed: list = [[] for _ in range(n_screens)]
        self.passing: list = [[] for _ in range(n_screens)]
        self.screened: list = [{} for _ in range(n_screens)]
        self.scored: dict = {}  # whether each jackknifed knockout fails
        self.dose = 0.0

    def pool(self) -> list[int]:
        """List the sites neither critical nor kept."""
        return sorted(set(self.search.sites) - self.critical - self.kept)

    def known(self, deleted: frozenset[int], tier: int) -> bool | None:
        """Tell whether a knockout fails a screen, if its trials so far
        settle that: it fails if it contains a failing set, and passes if
        a knockout containing it passed."""
        if not deleted:
            return False  # the wildtype
        if deleted in self.screened[tier]:
            return self.screened[tier][deleted]
        if any(s <= deleted for s in self.failed[tier]):
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
        stats = self.search.stats
        answers, wave = {}, []
        for request in dict.fromkeys(requests):
            if request[0] == "screen":
                answers[request] = self.known(request[2], request[1])
            if answers.get(request) is None:
                wave.append(request)
        for request, answer in zip(wave, (yield wave) if wave else ()):
            answers[request] = answer
            if request[0] != "screen":
                stats["jackknife_trials"] += request[1] == "jackknife"
                continue
            _, tier, deleted = request
            stats["screen_trials"][tier] += 1
            self.screened[tier][deleted] = answer
            if answer and len(deleted) == 1:
                self.failed[tier].append(deleted)
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
            if not candidates or len(required) >= self.search.max_set_size:
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
        search = self.search
        if level < search.n_screens:
            return (yield [("screen", level, k) for k in knockouts])
        reps = search.jackknife_replicates
        new = [k for k in dict.fromkeys(knockouts) if k not in self.scored]
        if new:
            scores = yield [
                ("score", "jackknife", k, r) for k in new for r in range(reps)
            ]
            for j, deleted in enumerate(new):
                mine = scores[j * reps : (j + 1) * reps]
                self.scored[deleted] = None in mine or (
                    search.cost(search.controls.mean - sum(mine) / reps)
                    > search.usable
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
        if found not in self.failed[tier]:
            self.failed[tier].append(found)
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
        search = self.search
        self.dose = min(0.5, 2.0 / max(1, len(search.sites)))
        idle = 0  # rounds in a row whose failures retained nothing
        while True:
            search.phase = "ramp"
            pool = self.pool()
            draws = [
                search.draw(pool, self.dose)
                for _ in range(search.batch_size if self.dose < 1.0 else 0)
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
            search.phase = "shrink"
            shrunk = yield from self.together(
                [self.shrink(deleted, 0) for deleted in failing]
            )
            search.phase = "jackknife"
            yield from self.together(
                [
                    self.jackknife(found, 0)
                    for found in dict.fromkeys(shrunk)
                    if found is not None
                ]
            )
            for deleted, found in zip(failing, shrunk):
                rest = deleted - self.critical - self.kept
                if found is not None or search.n_screens < 2:
                    continue
                if (yield from self.screen([rest], 0))[0]:
                    search.phase = "bump"
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
        self.search.rng.shuffle(order)
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

    def run(self) -> Wave:
        """Run the screens: the ramp, then, until no kept site is
        released, a check of the whole pool and a sweep by each later
        screen.

        Returns
        -------
        Generator[list, list, dict]
            Yields waves and is sent their answers; returns the result, as
            `find_minimal_critical_sets_bisect` does.
        """
        search = self.search
        yield from self.ramp()
        while True:
            search.phase = "certify"
            yield from self.together([self.settle(self.pool(), 0)])
            for tier in range(1, search.n_screens):
                search.phase = "sweep"
                yield from self.halve(self.pool(), tier)
            if not self.release():
                break
        pool = self.pool()
        failed = (yield from self.screen([frozenset(pool)], 0))[0]
        return {
            "critical": sorted(self.critical),
            "redundant": [(tier, sorted(s)) for tier, s in self.redundant],
            "adding_up": [(tier, sorted(s)) for tier, s in self.adding_up],
            "kept": sorted(self.kept),
            "released": sorted(self.released),
            "pool": pool,
            "certified": not failed,
        }


def find_minimal_critical_sets_bisect(search: typing.Any) -> Wave:
    """Find, with a staged search's screens, the minimal sets of sites
    whose knockout fails, and retain enough of each that none is wholly
    deleted.

    A critical set is one whose knockout fails a screen. Random knockouts
    are screened at a dose that fails about half the time, and each
    failure is shrunk by bisection to a minimal critical set. A set of one
    is a critical site. A larger set is jackknifed: each member is put
    back in turn, and the rest tested with the next test up, the next
    screen or, after the last, long trials. If every such knockout is
    fine, the set is *redundant*, and one member is kept. If not, its
    losses *add up*, and each member that fails that test alone is
    critical. The dose rises as sites are retained, until the whole
    remaining pool passes when knocked out together. Each later screen
    then searches the pool by halving. Last, a member kept for a
    redundant set is released if the set has another member retained.

    The search assumes no rescue: a knockout that fails a screen fails it
    with more sites out, and one that passes does so with fewer.

    Parameters
    ----------
    search : StagedSearch
        The search, with its controls set, for its settings, random
        number generator and tallies. Its `tally` follows the critical and
        kept sites as they are found.

    Returns
    -------
    Generator[list, list, dict]
        Yields waves and is sent their answers; returns the `critical`
        sites, the `redundant` and `adding_up` sets (each as a screen's
        tier and the set's sorted sites), the `kept` and `released` sites,
        the `pool` of sites left to delete, and whether the pool was
        `certified`: whether it passed the first screen knocked out whole.
    """
    state = _CriticalSetSearch(search)
    search.tally = {"critical": state.critical, "kept": state.kept}
    return (yield from state.run())
