from .._knockout import ACCEPT, KnockoutSearch, search_churn, split


class DdminSearch(KnockoutSearch):
    """Parallel partition-union delta debugging: disjoint chunk knockouts,
    union / partial-union repair of passing chunks, bisection of the
    survivors."""

    policy = "ddmin"

    def search(self):
        """Generator: parallel partition-union delta debugging."""
        return (
            yield from self.partition_union(self.initial_chunks(), "ddmin")
        )

    def partition_union(self, k: int, kind: str, *, pivot=None):
        """Generator: parallel partition-union delta debugging, starting
        from ``k`` chunks. With ``pivot`` (a generator function), hand
        over to it once chunks stop passing."""
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


def churn(dispatch, trial_submissions, trial_payloads, memo):
    """Skeletonize by parallel partition-union delta debugging. See docs/skeletonization.md."""
    return search_churn(
        DdminSearch, dispatch, trial_submissions, trial_payloads
    )
