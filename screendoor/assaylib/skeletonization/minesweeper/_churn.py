from .._knockout import (
    ACCEPT,
    KnockoutSearch,
    accepted_sites,
    search_churn,
    singletons,
    split,
)


def minesweeper_stage2_segments(sites) -> list:
    """The 26 multi-scale Stage-2 deletion segments (Rees-Garbutt 2020)."""
    ordered = list(sites)
    m = len(ordered)
    raw = [frozenset(ordered)]
    for frac in (0.90, 0.80, 0.70, 0.60):
        k = max(1, min(m, round(frac * m)))
        raw += [frozenset(ordered[:k]), frozenset(ordered[m - k :])]
    for parts in (2, 3, 4, 8):
        raw += split(ordered, parts)
    return list(dict.fromkeys(filter(None, raw)))


class MinesweeperSearch(KnockoutSearch):
    """Exhaustive singleton screen, the 26 multi-scale Stage-2 segments
    over the non-essential sites, Stage-3 combination, then Stage-4
    recursive 8-group divide and conquer."""

    policy = "minesweeper"

    def search(self):
        """Generator: 4-stage Minesweeper divide and conquer (Rees-Garbutt
        2020)."""
        # Every site is screened, as in the original under an exact oracle.
        stage1 = yield from self.test_all(
            singletons(sorted(self.current)), "minesweeper_stage1"
        )
        if self.stopped:
            return "unresolved"
        non_essential = accepted_sites(stage1)
        full = frozenset(non_essential)
        if len(non_essential) < 2:
            if non_essential:
                self.commit(full, "minesweeper_stage1")
                return (yield from self.after_commit())
            return "pass"

        segments = self.untried(minesweeper_stage2_segments(non_essential))
        stage2 = yield from self.test_all(
            segments, "minesweeper_stage2", until=full
        )
        if ACCEPT in stage2.values():
            _, status = yield from self.take(
                stage2, "minesweeper_stage3", full
            )
            if status != "pass":
                return status
        if self.stopped:
            return "unresolved"

        while True:
            rem = [i for i in non_essential if i in self.current]
            if len(rem) < 2:
                return "pass"
            pending = self.untried(split(rem, min(8, len(rem))), 1)
            if not pending:
                return "pass"
            outcomes = yield from self.test_all(pending, "minesweeper_stage4")
            if self.stopped:
                return "unresolved"
            if ACCEPT not in outcomes.values():
                return "pass"
            _, status = yield from self.take(outcomes, "minesweeper_stage4")
            if status != "pass":
                return status


def churn(dispatch, trial_submissions, trial_payloads, memo):
    """Skeletonize by 4-stage Minesweeper divide and conquer. See docs/skeletonization.md."""
    return search_churn(
        MinesweeperSearch, dispatch, trial_submissions, trial_payloads
    )
