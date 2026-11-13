import math
import typing

from .._knockout import (
    ACCEPT,
    KnockoutSearch,
    accepted_sites,
    make_search_churn,
    singletons,
    split,
)


class GamaSearch(KnockoutSearch):
    """GAMA, the Guess/Add/Mate Algorithm of Rees-Garbutt et al. (2020),
    "Designing minimal genomes using whole-cell models", Nat. Commun.
    11:836.

    A single-site screen finds the non-essential sites; random large
    deletions within each of several sets of them (Guess); unions of
    viable ones across sets (Add); then a genetic algorithm over the
    largest viable deletions, which may knock any site out or back in
    (Mate). Where the paper is silent (how two parents combine, how many
    sites a mutation flips), this follows the authors' code
    (GriersonMarucciLab/whole_cell_modelling_suite and GAMA).

    Every deletion is tested against the wildtype, and only genotypes not
    yet tested are sent, `batch_size` per wave: the batch size sets the
    pace, not which deletions are tried.

    Parameters
    ----------
    sites : iterable of int
        The wildtype's sites.
    guess_sets : int, default 4
        Sets the candidates are split into.
    guess_subsets : int, default 400
        Random deletions drawn per set.
    guess_min_fraction : float, default 0.5
        Smallest guess, as a fraction of its set.
    add_combinations : int, default 3000
        Unions of viable guesses to try.
    elite_size : int, default 50
        Largest viable deletions kept as parents.
    mate_children : int, default 1000
        Children per generation.
    mate_generations : int, default 100
        Most generations.
    mate_patience : int or None, default 20
        Generations in a row without a larger deletion before stopping;
        None never stops early.
    mutation_probability : float, default 0.4
        Chance a child is mutated.
    mutation_mean : float, default 2.0
        Mean number of sites a mutation flips.
    **kwargs
        Passed to `KnockoutSearch`.

    Raises
    ------
    ValueError
        If a parameter is out of range.
    """

    policy = "gama"
    policy_kwargs = (
        "guess_sets",
        "guess_subsets",
        "guess_min_fraction",
        "add_combinations",
        "elite_size",
        "mate_children",
        "mate_generations",
        "mate_patience",
        "mutation_probability",
        "mutation_mean",
    )

    def __init__(
        self,
        sites: typing.Iterable[int],
        *,
        guess_sets: int = 4,
        guess_subsets: int = 400,
        guess_min_fraction: float = 0.5,
        add_combinations: int = 3000,
        elite_size: int = 50,
        mate_children: int = 1000,
        mate_generations: int = 100,
        mate_patience: int | None = 20,
        mutation_probability: float = 0.4,
        mutation_mean: float = 2.0,
        **kwargs: typing.Any,
    ) -> None:
        super().__init__(sites, **kwargs)
        counts = (
            guess_subsets,
            add_combinations,
            mate_children,
            mate_generations,
        )
        if min(guess_sets, elite_size) < 1 or min(counts) < 0:
            raise ValueError("gama needs a guess set, an elite, sizes >= 0")
        if mate_patience is not None and mate_patience < 1:
            raise ValueError("mate_patience must be positive or None")
        if not 0 < guess_min_fraction <= 1:
            raise ValueError("guess_min_fraction must be in (0, 1]")
        if not 0 <= mutation_probability <= 1 or mutation_mean <= 0:
            raise ValueError("invalid mutation_probability or mutation_mean")
        self.guess_sets = guess_sets
        self.guess_subsets = guess_subsets
        self.guess_min_fraction = guess_min_fraction
        self.add_combinations = add_combinations
        self.elite_size = elite_size
        self.mate_children = mate_children
        self.mate_generations = mate_generations
        self.mate_patience = mate_patience
        self.mutation_probability = mutation_probability
        self.mutation_mean = mutation_mean
        self.sites = sorted(self.original)
        self.elite: list = []  # the largest viable deletions, largest first

    def search(self) -> typing.Generator[dict, dict, str]:
        """Run the single-site screen, Guess, Add and Mate, then commit the
        largest viable deletion found.

        Returns
        -------
        Generator[dict, dict, str]
            Yields waves and is sent their verdicts; returns the search's
            status.
        """
        screen = yield from self.test_all(
            singletons(self.sites), "gama_screen"
        )
        if self.stopped:
            return "unresolved"
        candidates = accepted_sites(screen)
        if len(candidates) < 2:
            if candidates:
                self.commit(frozenset(candidates), "gama_screen")
                return (yield from self.after_commit())
            return "pass"
        self.stats["candidates"] = len(candidates)
        self.stats["deleted"] = {}
        self.promote(singletons(candidates))
        yield from self.guess_add_mate(candidates)
        self.commit(self.elite[0], "gama")
        if self.stopped:  # out of budget: the best so far, uncertified
            return "unresolved"
        return (yield from self.after_commit())

    def guess_add_mate(
        self, candidates: list[int]
    ) -> typing.Generator[dict, dict, None]:
        """Run the three stages, each promoting what it finds viable to the
        elite; return early if the search stops.

        Parameters
        ----------
        candidates : list of int
            The non-essential sites, ascending.

        Returns
        -------
        Generator[dict, dict, None]
            Yields waves and is sent their verdicts.
        """
        # Guess: random deletions of at least guess_min_fraction of each set
        k = min(self.guess_sets, len(candidates))
        guesses = [self.guess(sorted(s)) for s in split(candidates, k)]
        found = yield from self.viable(sum(guesses, []), "gama_guess")
        if self.stopped:
            return
        found = set(self.promote(found, "guess"))
        pools = [[d for d in g if d in found] for g in guesses]
        self.stats["guess_viable"] = [len(p) for p in pools]

        # Add: unions of one viable guess from each of two or more sets
        pools = [p for p in pools if p]
        if len(pools) >= 2:
            unions = []
            for _ in range(self.add_combinations):
                chosen = self.rng.sample(
                    pools, self.rng.randint(2, len(pools))
                )
                unions.append(
                    frozenset().union(*(self.rng.choice(p) for p in chosen))
                )
            found = yield from self.viable(unions, "gama_add")
            if self.stopped:
                return
            self.stats["add_viable"] = len(self.promote(found, "add"))

        # Mate: children of the elite, until no generation in
        # mate_patience has found a larger deletion
        best, stale = len(self.elite[0]), 0
        for generation in range(self.mate_generations):
            if stale == self.mate_patience or not self.mate_children:
                break
            children = [self.child() for _ in range(self.mate_children)]
            found = yield from self.viable(
                filter(None, children), f"gama_mate_{generation}"
            )
            if self.stopped:
                return
            self.promote(found, "mate")
            self.stats["generations"] = generation + 1
            stale += 1
            if len(self.elite[0]) > best:
                best, stale = len(self.elite[0]), 0

    def viable(
        self, masks: typing.Iterable[frozenset[int]], kind: str
    ) -> typing.Generator[dict, dict, list[frozenset[int]]]:
        """Find which of `masks` are viable to delete from the wildtype.

        Only genotypes not yet tested are sent. Nothing feeds the proposal
        memory, which is for proposals against one parent.

        Parameters
        ----------
        masks : iterable of frozenset of int
            The deletions to test.
        kind : str
            The phase, set as `phase`.

        Returns
        -------
        Generator[dict, dict, list of frozenset of int]
            Yields waves and is sent their verdicts; returns the masks
            whose deletion is accepted.
        """
        masks = list(dict.fromkeys(masks))
        new = [d for d in masks if self.original - d not in self.cache]
        yield from self.test_all(new, kind, remember=False)
        return [
            d for d in masks if self.cache.get(self.original - d) == ACCEPT
        ]

    def promote(
        self, masks: typing.Iterable[frozenset[int]], stage: str = ""
    ) -> list[frozenset[int]]:
        """Keep the `elite_size` largest of the elite and the viable
        `masks`, breaking ties at random.

        Parameters
        ----------
        masks : iterable of frozenset of int
            Viable deletions to add to the elite.
        stage : str, default ""
            If given, record the largest deletion so far under it in
            `stats["deleted"]`.

        Returns
        -------
        list of frozenset of int
            `masks`, as a list.
        """
        masks = list(masks)
        ranked = list(dict.fromkeys([*self.elite, *masks]))
        self.rng.shuffle(ranked)
        self.elite = sorted(ranked, key=len, reverse=True)[: self.elite_size]
        if stage:
            self.stats["deleted"][stage] = len(self.elite[0])
        return masks

    def guess(self, members: list[int]) -> list[frozenset[int]]:
        """Draw random deletions within one set: a size drawn evenly from
        `guess_min_fraction` of the set up to all of it, then that many of
        its sites.

        Parameters
        ----------
        members : list of int
            The set's sites.

        Returns
        -------
        list of frozenset of int
            `guess_subsets` draws, without repeats.
        """
        m = len(members)
        low = max(1, math.ceil(self.guess_min_fraction * m))
        masks = (
            frozenset(self.rng.sample(members, self.rng.randint(low, m)))
            for _ in range(self.guess_subsets)
        )
        return list(dict.fromkeys(masks))

    def child(self) -> frozenset[int]:
        """Mate two of the elite, as the authors' code does.

        The parents are drawn in proportion to their deletions' sizes. A
        random number of sites, chosen at random, is inherited from the
        first and the rest from the second. Then, with
        `mutation_probability`, a random number of sites (about
        exponential, with mean `mutation_mean`, and at least one) is
        flipped between deleted and kept, anywhere in the genome.

        Returns
        -------
        frozenset of int
            The child's deletion.
        """
        rng, n = self.rng, len(self.sites)
        (p1,) = rng.choices(self.elite, [len(d) for d in self.elite])
        rest = [d for d in self.elite if d != p1] or [p1]
        (p2,) = rng.choices(rest, [len(d) for d in rest])
        child = set(p1 & p2)
        # only where the parents differ does it matter which gives a site;
        # draw those sites' membership in a random take-sized subset
        take = rng.randrange(n)
        for seen, i in enumerate(sorted(p1 ^ p2)):
            from_first = rng.random() * (n - seen) < take
            take -= from_first
            if from_first == (i in p1):
                child.add(i)
        if rng.random() < self.mutation_probability:
            flips = 0
            while not flips:
                flips = round(rng.expovariate(1 / self.mutation_mean))
            child ^= set(rng.sample(self.sites, min(flips, n)))
        return frozenset(child)


def make_churn(
    *, num_control_trials: int = 40
) -> typing.Callable[[dict, list[dict], list[dict], list[dict]], list[dict]]:
    """Create a churn function that skeletonizes by GAMA, the
    Guess/Add/Mate genetic algorithm.

    See docs/skeletonization.md for the assay kwargs.

    Parameters
    ----------
    num_control_trials : int, default 40
        How many times the wildtype runs, as the controls every genotype's
        scores are judged against.

    Returns
    -------
    Callable[[dict, list[dict], list[dict], list[dict]], list[dict]]
        The churn function, `churn(dispatch, trial_submissions,
        trial_payloads, memo)`.
    """
    return make_search_churn(GamaSearch, num_control_trials=num_control_trials)


churn = make_churn()
