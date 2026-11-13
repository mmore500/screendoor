"""The machinery the knockout policies share, ported from
knockout_skeleton.search (2026-11-03, exact-oracle mode).

A search is a generator. Where the original awaited
``evaluator.evaluate_many``, it yields ``{"genotypes": [...], "fresh": n}``
and is sent back ``{genotype: "accept" | "reject"}``, so churn can replay
it from recorded trial results on every tick: the same seed and verdicts
give the same trajectory. A genotype is the frozenset of retained sites; a
mask is a set of sites to delete from the current genotype.

Subclasses give the policy as ``search()``, a generator returning pass,
unresolved, recovered or exhausted_recovery; ``run()`` then makes the
sweep: it tries single deletions until none passes, and audits. Each wave
says whether it is in the ``sweep``, so the verdicts there may follow
another rule; with ``rejudge_at_sweep``, the search then forgets
its rejections, to have them judged again.
"""

import math
import random

from ....auxlib._weighted_subset import weighted_subset
from ._ProposalMemory import ProposalMemory
from ._masks import ACCEPT, UNKNOWN, singletons


class KnockoutSearch:
    policy = ""  # each subclass names its policy
    policy_kwargs: tuple = ()  # assay_kwargs its __init__ takes besides

    def __init__(
        self,
        sites,
        *,
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
        rejudge_at_sweep: bool = False,
        sweep: bool = True,
    ):
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        self.original = self.current = frozenset(sites)
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
        self.sweeping = False  # in the sweep, or the audit after search()
        self.rejudge_at_sweep = rejudge_at_sweep
        self.sweep = sweep
        self.stats: dict = {}  # a policy's own figures, for the summary

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
            got = yield {
                "genotypes": batch,
                "fresh": tag,
                "sweep": self.sweeping,
            }
            for s in batch:
                self.cache[s] = result[s] = got[s]
            if stop_after_accept and ACCEPT in result.values():
                break
        return result

    def test(self, masks, kind, *, stop_after_accept=False, remember=True):
        """Generator: verdicts for deleting each mask from the current
        genotype, as one proposal batch. They feed the proposal memory
        unless ``remember`` is false."""
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
        if remember:
            for d, v in result.items():
                self.memory.observe(parent, d, v)
        return result

    def test_all(self, masks, kind, *, until=None, remember=True):
        """Generator: test ``masks`` batch by batch, ending early if the
        search stops or the mask ``until`` is accepted."""
        outcomes: dict = {}
        for start in range(0, len(masks), self.b):
            batch = masks[start : start + self.b]
            outcomes.update(
                (yield from self.test(batch, kind, remember=remember))
            )
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

    def initial_chunks(self) -> int:
        size = self.initial_knockout_size
        if size is None:
            return 2
        return max(2, math.ceil(len(self.current) / size))

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
        """Generator: run ``search()``, then (unless ``sweep`` is false)
        singleton sweeps until no single deletion passes, and the final
        audit. Returns the result dict (``StopIteration.value``).
        """
        status = yield from self.search()
        if status in ("unresolved", "exhausted_recovery"):
            return self.result(False, status)
        self.sweeping = True
        if self.rejudge_at_sweep:  # judge it all again, by the sweep's rule
            self.cache.clear()
            self.memory.forget_rejections()
        if not self.sweep:  # so nothing certifies it minimal
            if self.final_audit and self.current != self.original:
                status = yield from self.audit()
                if status not in ("pass", "recovered"):
                    return self.result(False, "audit_" + status)
            return self.result(False, "sweep_skipped")
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
