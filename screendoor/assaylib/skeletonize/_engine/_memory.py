"""Contextual proposal memory, ported from knockout_skeleton.memory.

Verdicts are the strings "accept", "reject" and "unknown". No score here
certifies a genotype.
"""

import math


class ProposalMemory:
    def __init__(self, *, context_decay: float = 4.0, strength: float = 4.0):
        self.context_decay = context_decay
        self.strength = strength
        self._accepted: dict = {}  # an ordered set of (parent, mask)
        self._rejected: set = set()

    def observe(
        self, parent: frozenset, mask: frozenset, verdict: str
    ) -> None:
        if not mask <= parent:
            raise ValueError("a proposal mask must be contained in its parent")
        if verdict == "accept" and mask:
            self._accepted[parent, mask] = None
        elif verdict == "reject":
            # a rejected union never erases its accepted components
            self._rejected.add((parent, mask))

    def rejected_here(self, parent: frozenset, mask: frozenset) -> bool:
        return (parent, mask) in self._rejected

    def weights(self, current: frozenset) -> dict:
        """Sampling weight per site: higher where deletions were accepted
        in contexts like ``current``."""
        scores = dict.fromkeys(current, 0.0)
        for parent, mask in self._accepted:
            distance = len(parent ^ current) / max(1, len(parent))
            weight = math.exp(-self.context_decay * distance) / len(mask)
            for i in mask & current:
                scores[i] += weight
        return {
            i: 1 + self.strength * -math.expm1(-s) for i, s in scores.items()
        }

    def donors(self, current: frozenset) -> list:
        """Accepted masks, cut down to ``current``, largest first."""
        donors = {mask & current for _, mask in self._accepted}
        return sorted(
            donors - {frozenset()},
            key=lambda d: (len(d), tuple(sorted(d))),
            reverse=True,
        )


def weighted_subset(sites, size: int, weights: dict, rng) -> frozenset:
    """Weighted sampling without replacement, by exponential clocks."""
    if not 0 <= size <= len(sites):
        raise ValueError("invalid subset size")
    clocks = sorted(
        (-math.log(max(rng.random(), 1e-300)) / weights.get(i, 1.0), i)
        for i in sorted(sites)
    )
    return frozenset(i for _, i in clocks[:size])
