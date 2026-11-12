"""GAMA, the Guess/Add/Mate Algorithm of Rees-Garbutt et al. (2020),
"Designing minimal genomes using whole-cell models", Nat. Commun. 11:836.

Where the paper is silent (how two parents combine, how many sites a
mutation flips), this follows the authors' genetic algorithm code
(GriersonMarucciLab/whole_cell_modelling_suite, GriersonMarucciLab/GAMA).
"""

import math

from .._knockout import (
    ACCEPT,
    KnockoutSearch,
    accepted_sites,
    search_churn,
    singletons,
    split,
)


class GamaSearch(KnockoutSearch):
    """A single-site screen; random large deletions within each of four
    sets of the non-essential sites (Guess); unions of viable ones across
    sets (Add); then a genetic algorithm over the largest viable deletions
    that may knock any site out or back in (Mate).

    Every deletion is tested against the wildtype, and only genotypes not
    yet tested are sent, ``batch_size`` per wave: the batch size sets the
    pace, not which deletions are tried.
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
        sites,
        *,
        guess_sets: int = 4,
        guess_subsets: int = 400,
        guess_min_fraction: float = 0.5,
        add_combinations: int = 3000,
        elite_size: int = 50,
        mate_children: int = 1000,
        mate_generations: int = 100,
        mate_patience=20,
        mutation_probability: float = 0.4,
        mutation_mean: float = 2.0,
        **kwargs,
    ):
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

    def search(self):
        """Generator: the single-site screen, Guess, Add and Mate; then
        commit the largest viable deletion found."""
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

    def guess_add_mate(self, candidates: list):
        """Generator: the three stages, each promoting what it finds viable
        to the elite. Returns early if the search stops."""
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

    def viable(self, masks, kind):
        """Generator: the ``masks`` whose deletion from the wildtype is
        accepted. Only genotypes not yet tested are sent. None feeds the
        proposal memory, which is for proposals against one parent."""
        masks = list(dict.fromkeys(masks))
        new = [d for d in masks if self.original - d not in self.cache]
        yield from self.test_all(new, kind, remember=False)
        return [
            d for d in masks if self.cache.get(self.original - d) == ACCEPT
        ]

    def promote(self, masks, stage: str = "") -> list:
        """Keep the ``elite_size`` largest of the elite and the viable
        ``masks``, ties broken at random. Returns ``masks``."""
        masks = list(masks)
        ranked = list(dict.fromkeys([*self.elite, *masks]))
        self.rng.shuffle(ranked)
        self.elite = sorted(ranked, key=len, reverse=True)[: self.elite_size]
        if stage:
            self.stats["deleted"][stage] = len(self.elite[0])
        return masks

    def guess(self, members: list) -> list:
        """Random deletions within one set: a size drawn evenly from
        ``guess_min_fraction`` of the set up to all of it, then that many
        of its sites."""
        m = len(members)
        low = max(1, math.ceil(self.guess_min_fraction * m))
        masks = (
            frozenset(self.rng.sample(members, self.rng.randint(low, m)))
            for _ in range(self.guess_subsets)
        )
        return list(dict.fromkeys(masks))

    def child(self) -> frozenset:
        """Mate two of the elite, as the authors' code does: parents drawn
        in proportion to their deletions' sizes; a random number of sites,
        chosen at random, inherited from the first and the rest from the
        second; then, with ``mutation_probability``, a random number of
        sites (about exponential, mean ``mutation_mean``, at least one)
        flipped between deleted and kept, anywhere in the genome."""
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


def churn(dispatch, trial_submissions, trial_payloads, memo):
    """Skeletonize by GAMA, the Guess/Add/Mate genetic algorithm. See docs/skeletonization.md."""
    return search_churn(
        GamaSearch, dispatch, trial_submissions, trial_payloads
    )
