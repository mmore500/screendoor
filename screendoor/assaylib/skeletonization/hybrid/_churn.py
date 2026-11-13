import typing

from .._knockout import (
    ACCEPT,
    accepted_sites,
    make_search_churn,
    singletons,
    split,
)
from ..ddmin._churn import DdminSearch


def multi_dose_probes(
    sites: list[int], batch_size: int, *, include_full: bool = False
) -> list[frozenset]:
    """Pack a dose ladder (100%, 50%, 25% and 12.5% of `sites`) into one
    batch of probe masks.

    Parameters
    ----------
    sites : list of int
        The sites to probe, in order.
    batch_size : int
        The most probes to return.
    include_full : bool, default False
        Whether to include the 100% dose, all of `sites`.

    Returns
    -------
    list of frozenset
        The probe masks, each of at least two sites, without repeats.
    """
    ordered = list(sites)
    raw = [frozenset(ordered)] if include_full else []
    raw += split(ordered, 2) + split(ordered, 4)
    eighths = split(ordered, 8)
    raw += [eighths[i] for i in (1, 6, 3, 4, 2, 5, 0, 7)]
    probes = dict.fromkeys(seg for seg in raw if len(seg) >= 2)
    return list(probes)[: max(0, batch_size)]


class HybridSearch(DdminSearch):
    """One multi-dose pilot batch (50/25/12.5% doses); then top-down ddmin
    (`DdminSearch.partition_union`) with pivots to a bottom-up singleton
    sieve and subspace reduction."""

    policy = "hybrid"

    def search(self) -> typing.Generator[dict, dict, str]:
        """Run the multi-dose pilot, then top-down ddmin with pivots to the
        bottom-up sieve.

        Returns
        -------
        Generator[dict, dict, str]
            Yields waves and is sent their verdicts; returns the search's
            status.
        """
        sites = sorted(self.current)
        m = len(sites)
        k = self.initial_chunks()
        if m >= 8 and self.b >= 6 and self.initial_knockout_size is None:
            probes = self.untried(multi_dose_probes(sites, self.b))
            if probes:
                outcomes = yield from self.test(probes, "hybrid_dose_probe")
                if self.stopped:
                    return "unresolved"
                if ACCEPT not in outcomes.values():
                    return (yield from self.sieve())
                mask, status = yield from self.take(
                    outcomes, "hybrid_dose_probe"
                )
                if status != "pass":
                    return status
                finest = split(sites, 8 if m >= 16 and self.b >= 12 else 4)
                k = max(2, 2 * sum(not c <= mask for c in finest))
        return (
            yield from self.partition_union(
                k, "hybrid_ddmin", pivot=self.sieve
            )
        )

    def sieve(self) -> typing.Generator[dict, dict, str]:
        """Run the bottom-up singleton sieve, then top-down reduction of
        the non-essential sites.

        Returns
        -------
        Generator[dict, dict, str]
            Yields waves and is sent their verdicts; returns the search's
            status.
        """
        singles = self.untried(singletons(sorted(self.current)), 1)
        if not singles:
            return "pass"
        stage1 = yield from self.test_all(singles, "hybrid_stage1")
        if self.stopped:
            return "unresolved"
        non_essential = accepted_sites(stage1)
        full = frozenset(non_essential)
        if len(non_essential) < 2:
            if non_essential:
                self.commit(full, "hybrid_stage1")
                return (yield from self.after_commit())
            return "pass"

        probes = multi_dose_probes(non_essential, self.b, include_full=True)
        outcomes = yield from self.test(
            self.untried(probes), "hybrid_subspace_probe"
        )
        if self.stopped:
            return "unresolved"
        if ACCEPT in outcomes.values():
            _, status = yield from self.take(
                outcomes, "hybrid_subspace_probe", full
            )
            if status != "pass":
                return status

        k = 4
        while True:
            rem = [i for i in non_essential if i in self.current]
            m = len(rem)
            if m < 2 or k >= m:
                return "pass"
            chunks = split(rem, k)
            pending = self.untried(chunks)
            mask = None
            for start in range(0, len(pending), self.b):
                outcomes = yield from self.test(
                    pending[start : start + self.b], "hybrid_subspace_ddmin"
                )
                if self.stopped:
                    return "unresolved"
                if ACCEPT in outcomes.values():
                    mask, status = yield from self.take(
                        outcomes, "hybrid_subspace_ddmin"
                    )
                    if status != "pass":
                        return status
                    break
            if mask is not None:
                k = max(2, 2 * sum(not c <= mask for c in chunks))
            elif max(map(len, chunks)) <= 2:
                return "pass"
            else:
                k = min(m, 2 * k)


def make_churn(
    *, num_control_trials: int = 40
) -> typing.Callable[[dict, list[dict], list[dict], list[dict]], list[dict]]:
    """Create a churn function that skeletonizes by a multi-dose pilot,
    then top-down ddmin with pivots to a bottom-up singleton sieve.

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
    return make_search_churn(
        HybridSearch, num_control_trials=num_control_trials
    )


churn = make_churn()
