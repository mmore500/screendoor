import typing

from .._knockout import ACCEPT, KnockoutSearch, make_search_churn, split


class DdminSearch(KnockoutSearch):
    """Parallel partition-union delta debugging: disjoint chunk knockouts,
    union / partial-union repair of passing chunks, bisection of the
    survivors."""

    policy = "ddmin"

    def search(self) -> typing.Generator[dict, dict, str]:
        """Generator: parallel partition-union delta debugging.

        Returns
        -------
        Generator[dict, dict, str]
            Yields genotype batches, is sent their verdicts, and returns
            the search's status.
        """
        return (
            yield from self.partition_union(self.initial_chunks(), "ddmin")
        )

    def partition_union(
        self,
        k: int,
        kind: str,
        *,
        pivot: typing.Callable[[], typing.Generator[dict, dict, str]]
        | None = None,
    ) -> typing.Generator[dict, dict, str]:
        """Generator: parallel partition-union delta debugging, starting
        from ``k`` chunks. With ``pivot`` (a generator function), hand
        over to it once chunks stop passing.

        Parameters
        ----------
        k : int
            How many chunks to start from.
        kind : str
            The phase, recorded as the reason for each commit.
        pivot : Callable[[], Generator] or None, default None
            The search to hand over to.

        Returns
        -------
        Generator[dict, dict, str]
            Yields genotype batches, is sent their verdicts, and returns
            the search's status.
        """
        while len(self.current) >= 2 and k < len(self.current):
            small = self.exact and k >= 8 and len(self.current) <= 2 * self.b
            if pivot and small:
                return (yield from pivot())
            m = len(self.current)
            chunks = split(sorted(self.current), k)
            pending = self.untried(chunks)
            committed = False
            for start in range(0, len(pending), self.b):
                batch = [
                    c
                    for c in self.untried(pending[start : start + self.b])
                    if c <= self.current
                ]
                if not batch:
                    continue
                outcomes = yield from self.test(batch, kind)
                if self.stopped:
                    return "unresolved"
                if ACCEPT in outcomes.values():
                    _, status = yield from self.take(outcomes, kind)
                    if status != "pass":
                        return status
                    committed = True
            if max(map(len, chunks)) <= 2:
                break
            pristine = self.exact or self.current == self.original
            if committed:
                k = max(2, 2 * sum(c <= self.current for c in chunks))
            elif pivot and pending and k >= 4 and pristine:
                return (yield from pivot())
            else:
                k = min(m, 2 * k)
        return "pass"


def make_churn(
    *, num_control_trials: int = 40
) -> typing.Callable[[dict, list[dict], list[dict], list[dict]], list[dict]]:
    """Skeletonize by parallel partition-union delta debugging.

    See docs/skeletonization.md.

    Parameters
    ----------
    num_control_trials : int, default 40
        How many times the wildtype runs, as the controls every genotype's
        scores are judged against.

    Returns
    -------
    Callable
        The churn function, ``churn(dispatch, trial_submissions,
        trial_payloads, memo) -> actions``.
    """
    return make_search_churn(
        DdminSearch, num_control_trials=num_control_trials
    )


churn = make_churn()
