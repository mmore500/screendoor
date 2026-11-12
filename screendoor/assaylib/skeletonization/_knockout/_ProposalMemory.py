"""Contextual proposal memory, ported from knockout_skeleton.memory.

Verdicts are the strings "accept", "reject" and "unknown". No score here
certifies a genotype.
"""

import math


class ProposalMemory:
    """The verdicts on past deletions, by the genotype each was made from.

    Parameters
    ----------
    context_decay : float, default 4.0
        How fast an accepted deletion counts for less as its parent differs
        from the current genotype.
    strength : float, default 4.0
        The most a site's weight can rise above 1.
    """

    def __init__(
        self, *, context_decay: float = 4.0, strength: float = 4.0
    ) -> None:
        self.context_decay = context_decay
        self.strength = strength
        self._accepted: dict = {}  # an ordered set of (parent, mask)
        self._rejected: set = set()

    def observe(
        self, parent: frozenset, mask: frozenset, verdict: str
    ) -> None:
        """Record the verdict on deleting ``mask`` from ``parent``.

        Parameters
        ----------
        parent : frozenset
            The genotype the deletion was made from.
        mask : frozenset
            The sites deleted.
        verdict : str
            ``accept``, ``reject`` or ``unknown``.

        Raises
        ------
        ValueError
            If ``mask`` is not contained in ``parent``.
        """
        if not mask <= parent:
            raise ValueError("a proposal mask must be contained in its parent")
        if verdict == "accept" and mask:
            self._accepted[parent, mask] = None
        elif verdict == "reject":
            # a rejected union never erases its accepted components
            self._rejected.add((parent, mask))

    def rejected_here(self, parent: frozenset, mask: frozenset) -> bool:
        """Whether deleting ``mask`` from ``parent`` was rejected.

        Parameters
        ----------
        parent : frozenset
            The genotype the deletion was made from.
        mask : frozenset
            The sites deleted.

        Returns
        -------
        bool
            True if that deletion was rejected.
        """
        return (parent, mask) in self._rejected

    def weights(self, current: frozenset) -> dict[int, float]:
        """Sampling weight per site: higher where deletions were accepted
        in contexts like ``current``.

        Parameters
        ----------
        current : frozenset
            The current genotype.

        Returns
        -------
        dict of {int: float}
            The weight of each site in ``current``, from 1 to
            ``1 + strength``.
        """
        scores = dict.fromkeys(current, 0.0)
        for parent, mask in self._accepted:
            distance = len(parent ^ current) / max(1, len(parent))
            weight = math.exp(-self.context_decay * distance) / len(mask)
            for i in mask & current:
                scores[i] += weight
        return {
            i: 1 + self.strength * -math.expm1(-s) for i, s in scores.items()
        }

    def donors(self, current: frozenset) -> list[frozenset]:
        """Accepted masks, cut down to ``current``, largest first.

        Parameters
        ----------
        current : frozenset
            The current genotype.

        Returns
        -------
        list of frozenset
            The nonempty masks, without repeats.
        """
        donors = {mask & current for _, mask in self._accepted}
        return sorted(
            donors - {frozenset()},
            key=lambda d: (len(d), tuple(sorted(d))),
            reverse=True,
        )
