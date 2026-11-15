import math
import random
import typing

from ....auxlib._weighted_subset import weighted_subset
from ._ProposalMemory import ProposalMemory
from ._masks import ACCEPT, REJECT, UNKNOWN, singletons


class KnockoutSearch:
    """Base class of the knockout skeletonization policies, ported from
    `knockout_skeleton.search` (2026-11-03, exact-oracle mode).

    A search is a generator. Where the original awaited
    `evaluator.evaluate_many`, it yields a wave `{"genotypes": [...],
    "fresh": n, "sweep": bool}` and is sent back `{genotype: "accept" |
    "reject"}`, so that churn can replay it from recorded trial results on
    every tick: the same seed and verdicts give the same trajectory. A
    genotype is the frozenset of retained sites; a mask is a set of sites
    to delete from the current genotype.

    Subclasses give their policy as `search()`, a generator returning
    `pass`, `unresolved`, `recovered` or `exhausted_recovery`; `run()` then
    makes the sweep, trying single deletions until none passes, and
    audits. Each wave says whether it is in the sweep, so that verdicts
    there may follow another rule; with `rejudge_at_sweep`, the search
    then forgets its rejections, to have them judged again.

    Parameters
    ----------
    sites : iterable of int
        The wildtype's sites.
    batch_size : int
        Genotypes per wave.
    seed : int
        Seed of the search's own random number generator.
    combination_rounds : int, default 2
        Rounds of union proposals after accepted masks.
    exact : bool, default True
        Exact-oracle mode, as in the original.
    final_audit : bool, default True
        Whether to re-test the skeleton afresh before certifying it.
    audit_every : int, default 0
        Also audit after every this many commits; 0 never does.
    audit_adaptive : bool, default False
        Whether audits pace themselves: each one that passes doubles
        `audit_every`, and each that fails halves it. A failed audit then
        sifts what was deleted since the last one that passed, by
        halves: a part an audit accepts stays deleted, and a site that
        fails alone goes back in, and is not deleted again. Nothing rolls
        back, and the result is the newest audited genotype, with no
        commit unaudited.
    max_rollbacks : int, default 2
        Failed audits tolerated before giving up.
    max_proposal_batches : int or None, default None
        Stop, uncertified, after this many proposal batches.
    initial_knockout_size : int or None, default None
        Sites per initial ddmin chunk; None halves the genome.
    context_decay : float, default 4.0
        The proposal memory's `context_decay`.
    memory_strength : float, default 4.0
        The proposal memory's `strength`.
    rejudge_at_sweep : bool, default False
        Whether to forget verdicts at the sweep, to have them judged again
        by its rule.
    sweep : bool, default True
        Whether to run the singleton sweep after `search()`.
    """

    policy = ""  # each subclass names its policy
    policy_kwargs: tuple = ()  # the assay_kwargs its __init__ takes besides

    def __init__(
        self,
        sites: typing.Iterable[int],
        *,
        batch_size: int,
        seed: int,
        combination_rounds: int = 2,
        exact: bool = True,
        final_audit: bool = True,
        audit_every: int = 0,
        audit_adaptive: bool = False,
        max_rollbacks: int = 2,
        max_proposal_batches: int | None = None,
        initial_knockout_size: int | None = None,
        context_decay: float = 4.0,
        memory_strength: float = 4.0,
        rejudge_at_sweep: bool = False,
        sweep: bool = True,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        self.original = self.current = frozenset(sites)
        self.b = batch_size
        self.rng = random.Random(seed)
        self.combination_rounds = combination_rounds
        self.exact = exact
        self.final_audit = final_audit
        self.audit_every = audit_every
        self.audit_adaptive = audit_adaptive
        self.audited = 0  # the newest checkpoint an audit accepted
        self.excluded: set = set()  # sites that audits put back in
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

    def evaluate(
        self,
        candidates: typing.Iterable[frozenset[int]],
        *,
        stop_after_accept: bool = False,
        fresh: bool = False,
    ) -> typing.Generator[dict, dict, dict]:
        """Get verdicts on genotypes, as `ExactEvaluator.evaluate_many`
        did.

        Cached verdicts are reused unless `fresh`; the rest are asked for
        in waves of `batch_size`.

        Parameters
        ----------
        candidates : iterable of frozenset of int
            The genotypes to judge.
        stop_after_accept : bool, default False
            Whether to stop once a wave accepts a genotype.
        fresh : bool, default False
            Whether to bypass the cache, asking for new trials.

        Returns
        -------
        Generator[dict, dict, dict]
            Yields waves and is sent their verdicts; returns `{genotype:
            verdict}`, with `UNKNOWN` for genotypes not asked about.
        """
        candidates = list(dict.fromkeys(candidates))
        result, pending = {}, []
        for s in candidates:
            if not fresh and not self.excluded <= s:
                self.cache[s] = REJECT  # it deletes what an audit put back
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

    def test(
        self,
        masks: typing.Iterable[frozenset[int]],
        kind: str,
        *,
        stop_after_accept: bool = False,
        remember: bool = True,
    ) -> typing.Generator[dict, dict, dict]:
        """Get verdicts on deleting each mask from the current genotype, as
        one proposal batch.

        The verdicts feed the proposal memory unless `remember` is False.
        Once `max_proposal_batches` is spent, the search is stopped and
        every mask is `UNKNOWN`.

        Parameters
        ----------
        masks : iterable of frozenset of int
            Nonempty subsets of the current genotype.
        kind : str
            The phase, set as `phase`.
        stop_after_accept : bool, default False
            Whether to stop once a wave accepts a genotype.
        remember : bool, default True
            Whether the verdicts feed the proposal memory.

        Returns
        -------
        Generator[dict, dict, dict]
            Yields waves and is sent their verdicts; returns `{mask:
            verdict}`.
        """
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

    def test_all(
        self,
        masks: list[frozenset[int]],
        kind: str,
        *,
        until: frozenset[int] | None = None,
        remember: bool = True,
    ) -> typing.Generator[dict, dict, dict]:
        """Test `masks` batch by batch, stopping early if the search stops
        or the mask `until` is accepted.

        Parameters
        ----------
        masks : list of frozenset of int
            Nonempty subsets of the current genotype.
        kind : str
            The phase, set as `phase`.
        until : frozenset of int or None, default None
            A mask whose acceptance ends the testing.
        remember : bool, default True
            Whether the verdicts feed the proposal memory.

        Returns
        -------
        Generator[dict, dict, dict]
            Yields waves and is sent their verdicts; returns `{mask:
            verdict}` for the masks tested.
        """
        outcomes: dict = {}
        for start in range(0, len(masks), self.b):
            batch = masks[start : start + self.b]
            outcomes.update(
                (yield from self.test(batch, kind, remember=remember))
            )
            if self.stopped or outcomes.get(until) == ACCEPT:
                break
        return outcomes

    def untried(
        self, masks: typing.Iterable[frozenset[int]], min_size: int = 2
    ) -> list[frozenset[int]]:
        """Filter `masks` to those of at least `min_size` sites not yet
        rejected from the current genotype."""
        return [
            d
            for d in masks
            if len(d) >= min_size
            and not self.memory.rejected_here(self.current, d)
        ]

    def _best(self, masks: typing.Iterable[frozenset[int]]) -> frozenset[int]:
        """Pick a largest mask, breaking ties at random."""
        masks = list(masks)
        size = max(map(len, masks))
        largest = [d for d in masks if len(d) == size]
        return self.rng.choice(sorted(largest, key=lambda d: tuple(sorted(d))))

    def combination_masks(
        self, accepted: set, attempted: set
    ) -> list[frozenset[int]]:
        """Propose unions of accepted masks larger than the best one.

        Parameters
        ----------
        accepted : set of frozenset of int
            The masks accepted so far.
        attempted : set of frozenset of int
            The masks already proposed, not to propose again.

        Returns
        -------
        list of frozenset of int
            At most `batch_size` proposals.
        """
        best = self._best(accepted)
        donors = sorted(
            accepted, key=lambda d: (len(d), tuple(sorted(d))), reverse=True
        )
        donors = list(dict.fromkeys(donors + self.memory.donors(self.current)))
        proposals, seen = [], set(attempted)

        def add(d: typing.Iterable[int]) -> None:
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

    def combine(
        self, outcomes: dict
    ) -> typing.Generator[dict, dict, frozenset[int]]:
        """Find the best mask among the accepted ones and their accepted
        unions, over `combination_rounds` rounds of proposals.

        Parameters
        ----------
        outcomes : dict of {frozenset of int: str}
            The verdict on each mask of a proposal batch, at least one of
            them `ACCEPT`.

        Returns
        -------
        Generator[dict, dict, frozenset of int]
            Yields waves and is sent their verdicts; returns the best mask.
        """
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

    def commit(self, mask: frozenset[int], reason: str) -> None:
        """Delete `mask` from the current genotype, recording the
        transition and a checkpoint."""
        old = self.current
        self.current = old - mask
        if not self.current < old:
            raise AssertionError("commits must strictly delete sites")
        self.transitions.append((old, self.current, "deletion", reason))
        self.checkpoints.append(self.current)
        self.commits_since_audit += 1

    def sift(
        self, good: frozenset[int], block: list[int], fails: bool
    ) -> typing.Generator[dict, dict, frozenset[int]]:
        """Delete from `good`, a genotype that audits accept, as much of
        `block` as they also accept, by halves: a part that passes is
        deleted, and a site that fails alone is excluded.

        Parameters
        ----------
        good : frozenset of int
            A genotype that an audit accepted.
        block : list of int
            Sites of it to delete.
        fails : bool
            Whether deleting the whole block is known to fail.

        Returns
        -------
        Generator[dict, dict, frozenset of int]
            Yields waves and is sent their verdicts; returns the genotype
            left, which an audit accepted.
        """
        after = good - frozenset(block)
        if not fails:
            verdict = (yield from self.evaluate([after], fresh=True))[after]
            if verdict == ACCEPT:
                return after
        if len(block) == 1:
            self.excluded.update(block)
            return good
        left, right = block[: len(block) // 2], block[len(block) // 2 :]
        good = yield from self.sift(good, left, False)
        # with all of the left half out, the right fails as the block did
        fails = good == after | frozenset(right)
        return (yield from self.sift(good, right, fails))

    def audit(self) -> typing.Generator[dict, dict, str]:
        """Re-evaluate the current genotype afresh and, if it fails, roll
        back to the newest checkpoint that still passes; if
        `audit_adaptive`, instead put back the sites that fail, by `sift`.

        Returns
        -------
        Generator[dict, dict, str]
            Yields waves and is sent their verdicts; returns `pass`,
            `unresolved`, `recovered` or `exhausted_recovery`.
        """
        target = self.current
        if self.audit_adaptive and target == self.checkpoints[self.audited]:
            return "pass"  # an audit accepted it already
        self.phase = "audit"
        verdict = (yield from self.evaluate([target], fresh=True))[target]
        self.memory.observe(target, frozenset(), verdict)
        self.commits_since_audit = 0
        if verdict == ACCEPT:
            self.audited = len(self.checkpoints) - 1
            if self.audit_adaptive:
                self.audit_every *= 2
            return "pass"
        if verdict == UNKNOWN:
            return "unresolved"
        self.rollbacks += 1
        if self.audit_adaptive:
            good = self.checkpoints[self.audited]
            self.current = yield from self.sift(
                good, sorted(good - target), True
            )
            self.checkpoints.append(self.current)
            chosen = len(self.checkpoints) - 1
            self.audit_every = max(1, self.audit_every // 2)
        else:
            chosen = 0
            for index in range(len(self.checkpoints) - 2, 0, -1):
                cp = self.checkpoints[index]
                if (yield from self.evaluate([cp], fresh=True))[cp] == ACCEPT:
                    chosen = index
                    break
            self.current = self.checkpoints[chosen]
            self.checkpoints = self.checkpoints[: chosen + 1]
        self.audited = chosen
        self.transitions.append(
            (target, self.current, "rollback", "fresh_audit_rejected")
        )
        if self.rollbacks > self.max_rollbacks:
            return "exhausted_recovery"
        return "recovered"

    def after_commit(self) -> typing.Generator[dict, dict, str]:
        """Audit if `audit_every` commits have gone unaudited; else pass.

        Returns
        -------
        Generator[dict, dict, str]
            Yields waves and is sent their verdicts; returns the audit's
            status, or `pass` without one.
        """
        if self.audit_every and self.commits_since_audit >= self.audit_every:
            return (yield from self.audit())
        return "pass"

    def take(
        self,
        outcomes: dict,
        reason: str,
        full: frozenset[int] | None = None,
    ) -> typing.Generator[dict, dict, tuple[frozenset[int], str]]:
        """Commit `full` if it was accepted, else the best combination of
        the accepted masks; then audit as `after_commit` does.

        Parameters
        ----------
        outcomes : dict of {frozenset of int: str}
            The verdict on each mask of a proposal batch.
        reason : str
            Recorded with the commit's transition.
        full : frozenset of int or None, default None
            The mask to prefer if it was accepted.

        Returns
        -------
        Generator[dict, dict, tuple]
            Yields waves and is sent their verdicts; returns the mask
            committed and the audit's status.
        """
        if outcomes.get(full) == ACCEPT:
            mask = full
        else:
            mask = yield from self.combine(outcomes)
        self.commit(mask, reason)
        return mask, (yield from self.after_commit())

    def initial_chunks(self) -> int:
        """Return how many chunks ddmin starts from: 2, or enough for
        chunks of `initial_knockout_size` sites."""
        size = self.initial_knockout_size
        if size is None:
            return 2
        return max(2, math.ceil(len(self.current) / size))

    def result(
        self,
        certified: bool,
        reason: str,
        unresolved: typing.Iterable[int] = (),
    ) -> dict:
        """Build the search's result.

        Parameters
        ----------
        certified : bool
            Whether the skeleton is certified single-deletion minimal.
        reason : str
            The search's `status`.
        unresolved : iterable of int, default ()
            Sites whose single deletions went unresolved.

        Returns
        -------
        dict
            `retained`, `certified`, `status`, `proposal_batches`,
            `rollbacks`, `transitions` and `unresolved`.
        """
        # with adaptive audits, only what an audit accepted
        retained = self.current
        if self.audit_adaptive:
            retained = self.checkpoints[self.audited]
        return {
            "retained": retained,
            "certified": certified,
            "status": reason,
            "proposal_batches": self.batches,
            "rollbacks": self.rollbacks,
            "transitions": list(self.transitions),
            "unresolved": sorted(unresolved),
        }

    def run(self) -> typing.Generator[dict, dict, dict]:
        """Run `search()`, then, unless `sweep` is False, singleton sweeps
        until no single deletion passes, and the final audit.

        Returns
        -------
        Generator[dict, dict, dict]
            Yields waves and is sent their verdicts; returns the result, as
            `result` builds it.
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
