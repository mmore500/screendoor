"""Replayable port of knockout_skeleton.search (2026-11-03): the ``ddmin``,
``minesweeper`` and ``hybrid`` policies in exact-oracle mode.

The search is a generator. Where the original awaited
``evaluator.evaluate_many``, it yields ``{"genotypes": [...], "fresh": n}``
and is sent back ``{genotype: "accept" | "reject"}``. Churn can therefore
replay the whole search from recorded trial results on every tick: the same
seed and verdicts give the same trajectory.

A genotype is the frozenset of retained sites; a mask is a set of sites to
delete from the current genotype.
"""

import math
import random

from ._memory import ProposalMemory, weighted_subset

POLICIES = ("ddmin", "minesweeper", "hybrid")
ACCEPT, REJECT, UNKNOWN = "accept", "reject", "unknown"


def split(sites: list, k: int) -> list:
    """Cut ``sites`` into ``k`` consecutive, near-equal chunks."""
    m = len(sites)
    return [frozenset(sites[i * m // k : (i + 1) * m // k]) for i in range(k)]


def singletons(sites) -> list:
    return [frozenset([i]) for i in sites]


def accepted_sites(outcomes: dict) -> list:
    return sorted(i for d, v in outcomes.items() if v == ACCEPT for i in d)


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


def multi_dose_probes(sites, batch_size: int, *, include_full=False) -> list:
    """Pack a dose ladder (100%, 50%, 25%, 12.5%) into one batch."""
    ordered = list(sites)
    raw = [frozenset(ordered)] if include_full else []
    raw += split(ordered, 2) + split(ordered, 4)
    eighths = split(ordered, 8)
    raw += [eighths[i] for i in (1, 6, 3, 4, 2, 5, 0, 7)]
    probes = dict.fromkeys(seg for seg in raw if len(seg) >= 2)
    return list(probes)[: max(0, batch_size)]


class Search:
    def __init__(
        self,
        sites,
        *,
        policy: str,
        batch_size: int,
        seed,
        combination_rounds: int = 2,
        exact: bool = True,
        final_audit: bool = True,
        audit_every: int = 0,
        max_rollbacks: int = 2,
        max_proposal_batches=None,
        initial_knockout_size=None,
        context_decay: float = 4.0,
        memory_strength: float = 4.0,
    ):
        if policy not in POLICIES:
            raise ValueError(f"unknown policy {policy!r}; use {POLICIES}")
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        self.original = self.current = frozenset(sites)
        self.policy = policy
        self.b = batch_size
        self.rng = random.Random(seed)
        self.combination_rounds = combination_rounds
        self.exact = exact
        self.final_audit = final_audit
        self.audit_every = audit_every
        self.max_rollbacks = max_rollbacks
        self.max_proposal_batches = max_proposal_batches
        self.initial_knockout_size = initial_knockout_size
        self.memory = ProposalMemory(
            context_decay=context_decay, strength=memory_strength
        )
        self.cache: dict = {}  # genotype -> verdict
        self.fresh_count = 0
        self.transitions: list = []  # (before, after, kind, reason)
        self.checkpoints = [self.current]
        self.batches = 0
        self.rollbacks = 0
        self.commits_since_audit = 0
        self.stopped = ""  # why the search gave up, if it did
        self.phase = "start"

    # -- evaluation ------------------------------------------------------
    def evaluate(self, candidates, *, stop_after_accept=False, fresh=False):
        """Generator: verdicts for genotypes, as in
        ``ExactEvaluator.evaluate_many``. ``fresh`` bypasses the cache."""
        candidates = list(dict.fromkeys(candidates))
        result, pending = {}, []
        for s in candidates:
            if s in self.cache and not fresh:
                result[s] = self.cache[s]
            else:
                pending.append(s)
                result[s] = UNKNOWN
        if stop_after_accept and ACCEPT in result.values():
            return result
        for start in range(0, len(pending), self.b):
            batch = pending[start : start + self.b]
            tag = 0
            if fresh:
                self.fresh_count += 1
                tag = self.fresh_count
            got = yield {"genotypes": batch, "fresh": tag}
            for s in batch:
                self.cache[s] = result[s] = got[s]
            if stop_after_accept and ACCEPT in result.values():
                break
        return result

    def test(self, masks, kind, *, stop_after_accept=False):
        """Generator: verdicts for deleting each mask from the current
        genotype, as one proposal batch."""
        masks = list(dict.fromkeys(masks))
        if not masks:
            return {}
        limit = self.max_proposal_batches
        if limit is not None and self.batches >= limit:
            self.stopped = "proposal_batch_budget"
            return dict.fromkeys(masks, UNKNOWN)
        self.batches += 1
        self.phase = kind
        parent = self.current
        if any(not d or not d <= parent for d in masks):
            raise AssertionError("only nonempty deletion masks are allowed")
        outcomes = yield from self.evaluate(
            [parent - d for d in masks], stop_after_accept=stop_after_accept
        )
        result = {d: outcomes[parent - d] for d in masks}
        for d, v in result.items():
            self.memory.observe(parent, d, v)
        return result

    def test_all(self, masks, kind, *, until=None):
        """Generator: test ``masks`` batch by batch, ending early if the
        search stops or the mask ``until`` is accepted."""
        outcomes: dict = {}
        for start in range(0, len(masks), self.b):
            batch = masks[start : start + self.b]
            outcomes.update((yield from self.test(batch, kind)))
            if self.stopped or outcomes.get(until) == ACCEPT:
                break
        return outcomes

    def untried(self, masks, min_size: int = 2) -> list:
        """Masks of at least ``min_size`` not yet rejected here."""
        return [
            d
            for d in masks
            if len(d) >= min_size
            and not self.memory.rejected_here(self.current, d)
        ]

    # -- combination -----------------------------------------------------
    def _best(self, masks):
        """A largest mask, ties broken at random."""
        masks = list(masks)
        size = max(map(len, masks))
        largest = [d for d in masks if len(d) == size]
        return self.rng.choice(sorted(largest, key=lambda d: tuple(sorted(d))))

    def combination_masks(self, accepted: set, attempted: set) -> list:
        """Propose unions of accepted masks larger than the best one."""
        best = self._best(accepted)
        donors = sorted(
            accepted, key=lambda d: (len(d), tuple(sorted(d))), reverse=True
        )
        donors = list(dict.fromkeys(donors + self.memory.donors(self.current)))
        proposals, seen = [], set(attempted)

        def add(d):
            d = frozenset(d)
            if (
                len(d) > len(best)
                and d <= self.current
                and d not in seen
                and not self.memory.rejected_here(self.current, d)
            ):
                seen.add(d)
                proposals.append(d)

        add(frozenset().union(*accepted))
        full_quota = max(1, self.b // 2)
        for donor in donors:
            if len(proposals) >= full_quota:
                break
            add(best | donor)
        for _ in range(self.b * 20):
            if len(proposals) >= self.b or not donors:
                break
            donor = self.rng.choice(donors)
            extra = donor - best
            if extra:
                k = max(1, math.ceil(len(extra) / 2))
                add(best | frozenset(self.rng.sample(sorted(extra), k)))
            pool = frozenset().union(*donors)
            if len(pool) > len(best):
                k = len(best) + max(1, (len(pool) - len(best)) // 2)
                weights = self.memory.weights(self.current)
                add(weighted_subset(pool, k, weights, self.rng))
        return proposals[: self.b]

    def combine(self, outcomes: dict):
        """Generator: the best mask among the accepted ones and their
        accepted unions."""
        accepted = {d for d, v in outcomes.items() if v == ACCEPT}
        if not accepted:
            raise AssertionError("combination requires an accepted fallback")
        attempted = set(outcomes)
        for _ in range(self.combination_rounds):
            proposals = self.combination_masks(accepted, attempted)
            if not proposals or self.stopped:
                break
            results = yield from self.test(proposals, "combination")
            attempted.update(proposals)
            accepted.update(d for d, v in results.items() if v == ACCEPT)
        return self._best(accepted)

    def commit(self, mask, reason: str) -> None:
        old = self.current
        self.current = old - mask
        if not self.current < old:
            raise AssertionError("commits must strictly delete sites")
        self.transitions.append((old, self.current, "deletion", reason))
        self.checkpoints.append(self.current)
        self.commits_since_audit += 1

    def audit(self):
        """Generator: re-evaluate the current genotype afresh, rolling back
        to the newest checkpoint that still passes if it fails.

        Returns pass, unresolved, recovered or exhausted_recovery.
        """
        target = self.current
        self.phase = "audit"
        verdict = (yield from self.evaluate([target], fresh=True))[target]
        self.memory.observe(target, frozenset(), verdict)
        self.commits_since_audit = 0
        if verdict == ACCEPT:
            return "pass"
        if verdict == UNKNOWN:
            return "unresolved"
        self.rollbacks += 1
        chosen = 0
        for index in range(len(self.checkpoints) - 2, 0, -1):
            cp = self.checkpoints[index]
            if (yield from self.evaluate([cp], fresh=True))[cp] == ACCEPT:
                chosen = index
                break
        self.current = self.checkpoints[chosen]
        self.checkpoints = self.checkpoints[: chosen + 1]
        self.transitions.append(
            (target, self.current, "rollback", "fresh_audit_rejected")
        )
        if self.rollbacks > self.max_rollbacks:
            return "exhausted_recovery"
        return "recovered"

    def after_commit(self):
        if self.audit_every and self.commits_since_audit >= self.audit_every:
            return (yield from self.audit())
        return "pass"

    def take(self, outcomes: dict, reason: str, full=None):
        """Generator: commit ``full`` if it was accepted, else the best
        combination of the accepted masks. Returns (mask, audit status)."""
        if outcomes.get(full) == ACCEPT:
            mask = full
        else:
            mask = yield from self.combine(outcomes)
        self.commit(mask, reason)
        return mask, (yield from self.after_commit())

    # -- policies --------------------------------------------------------
    def initial_chunks(self) -> int:
        size = self.initial_knockout_size
        if size is None:
            return 2
        return max(2, math.ceil(len(self.current) / size))

    def partition_union(self, k: int, kind: str, *, sieve: bool = False):
        """Generator: parallel partition-union delta debugging, starting
        from ``k`` chunks. With ``sieve``, pivot to the bottom-up sieve
        once chunks stop passing."""
        while len(self.current) >= 2 and k < len(self.current):
            small = self.exact and k >= 8 and len(self.current) <= 2 * self.b
            if sieve and small:
                return (yield from self.sieve())
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
            elif sieve and pending and k >= 4 and pristine:
                return (yield from self.sieve())
            else:
                k = min(m, 2 * k)
        return "pass"

    def ddmin(self):
        """Generator: parallel partition-union delta debugging."""
        return (
            yield from self.partition_union(self.initial_chunks(), "ddmin")
        )

    def minesweeper(self):
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

    def sieve(self):
        """Generator: bottom-up singleton sieve, then top-down reduction of
        the non-essential sites."""
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

    def hybrid(self):
        """Generator: multi-dose pilot, then top-down ddmin with pivots to
        the bottom-up sieve."""
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
        return (yield from self.partition_union(k, "hybrid_ddmin", sieve=True))

    # -- driver ----------------------------------------------------------
    def result(self, certified: bool, reason: str, unresolved=()) -> dict:
        return {
            "retained": self.current,
            "certified": certified,
            "status": reason,
            "proposal_batches": self.batches,
            "rollbacks": self.rollbacks,
            "transitions": list(self.transitions),
            "unresolved": sorted(unresolved),
        }

    def run(self):
        """Generator: run the policy, then singleton sweeps until no single
        deletion passes. Returns the result dict (``StopIteration.value``).
        """
        status = yield from getattr(self, self.policy)()
        if status in ("unresolved", "exhausted_recovery"):
            return self.result(False, status)
        while True:
            if self.stopped:
                return self.result(False, self.stopped)
            self.phase = "singleton_sweep"
            masks = self.untried(singletons(sorted(self.current)), 1)
            self.rng.shuffle(masks)
            unresolved, outcomes = [], {}
            for start in range(0, len(masks), self.b):
                batch = yield from self.test(
                    masks[start : start + self.b],
                    "singleton",
                    stop_after_accept=True,
                )
                unresolved += [
                    i for d, v in batch.items() if v == UNKNOWN for i in d
                ]
                if ACCEPT in batch.values():
                    outcomes = batch
                    break
                if self.stopped:
                    return self.result(False, self.stopped, unresolved)
            if outcomes:
                mask = yield from self.combine(outcomes)
                self.commit(mask, "certified_proposal")
                status = yield from self.after_commit()
                if status in ("unresolved", "exhausted_recovery"):
                    return self.result(False, "audit_" + status)
                continue
            if unresolved:
                return self.result(
                    False, "singleton_tests_unresolved", unresolved
                )
            if self.final_audit and self.current != self.original:
                status = yield from self.audit()
                if status == "recovered":
                    continue
                if status != "pass":
                    return self.result(False, "audit_" + status)
            return self.result(True, "complete_singleton_certificate")
