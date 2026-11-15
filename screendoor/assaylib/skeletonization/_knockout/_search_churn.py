from collections import Counter
import math
from statistics import NormalDist
import typing

from .... import churn as scd_churn
from ....auxlib._canonical_json import canonical_json
from ....auxlib._encode_sites import encode_sites
from ._KnockoutSearch import KnockoutSearch
from ._SequentialTest import SEQUENTIAL_RULES, SequentialTest
from ._controls import RULES, Controls, t_quantile
from ._masks import ACCEPT, REJECT

SEARCH_KWARGS = (
    "combination_rounds",
    "exact",
    "final_audit",
    "audit_every",
    "audit_adaptive",
    "max_rollbacks",
    "max_proposal_batches",
    "initial_knockout_size",
    "context_decay",
    "memory_strength",
)


def _trial_key(g: frozenset[int], rep: int, fresh: int) -> dict:
    key = {"retained": encode_sites(g), "replicate": rep}
    if fresh:
        key["fresh"] = fresh
    return key


def _masked_sequence(kw: dict, g: frozenset[int]) -> str:
    nop = kw.get("nop_symbol", "A")
    return "".join(s if i in g else nop for i, s in enumerate(kw["sequence"]))


def _trial_env(kw: dict, n: int, g: frozenset[int], rep: int) -> dict:
    """Build a trial's environment: the user's `env`, then the assay's own
    variables, which win."""
    env = {
        **kw.get("env", {}),
        "retained": encode_sites(g),
        "knockout": encode_sites(frozenset(range(n)) - g),
        "n_sites": str(n),
        "replicate": str(rep),
    }
    if "sequence" in kw:
        env["sequence"] = _masked_sequence(kw, g)
        env["wildtype"] = kw["sequence"]  # e.g. to compete against
    return env


def _as_dict(result: typing.Any) -> dict:
    if isinstance(result, bool):
        return {"accept": result}
    if isinstance(result, (int, float)):
        return {"score": float(result)}
    if isinstance(result, dict):
        return result
    raise ValueError(
        f"trial result must be a bool, number or object: {result!r}"
    )


def _verdict(
    kw: dict,
    results: list,
    baseline: list,
    judge: typing.Callable[[list[float]], str | None],
    *,
    scores_only: bool = False,
) -> str | None:
    """Accept or reject a genotype from its replicates' results, given the
    wildtype controls' results, `baseline`.

    `judge(scores)` gives the verdict on the replicates' scores, or None if
    they do not decide yet; `scores_only` refuses `accept` results.
    """
    rs = [_as_dict(r) for r in results]
    baseline = [_as_dict(b) for b in baseline]
    if scores_only and any("accept" in r for r in rs):
        raise ValueError("this rule needs scores, not accept results")
    if any("accept" in r for r in rs):
        if not all("accept" in r for r in rs):
            raise ValueError("some results have 'accept' and some do not")
        fraction = sum(bool(r["accept"]) for r in rs) / len(rs)
        return ACCEPT if fraction >= kw.get("accept_fraction", 1.0) else REJECT
    if any(r.get("viable", True) is False for r in rs):
        return REJECT
    for r in [*rs, *baseline]:
        missing = [
            f for f in ("score", *kw.get("require_atleast", ())) if f not in r
        ]
        if missing:
            raise ValueError(f"trial result lacks {missing}: {r!r}")
    for field in kw.get("require_atleast", []):
        want = baseline[0][field]
        for r in rs:
            if len(r[field]) != len(want):
                raise ValueError(
                    f"{field!r} has {len(r[field])} entries, not {len(want)}"
                )
            if any(g < w for g, w in zip(r[field], want)):
                return REJECT
    return judge([float(r["score"]) for r in rs])


def _summary(
    kw: dict,
    search: KnockoutSearch,
    result: dict,
    n: int,
    trials: list[dict],
    waves: int,
    control: dict,
) -> dict:
    retained = result["retained"]
    summary = {
        "policy": search.policy,
        "n_sites": n,
        "retained": encode_sites(retained),
        "retained_count": len(retained),
        "certified": result["certified"],
        "status": result["status"],
        "proposal_batches": result["proposal_batches"],
        "rollbacks": result["rollbacks"],
        "waves": waves,
        "trials": len(trials),
        "transitions": [
            {
                "before": len(before),
                "after": len(after),
                "kind": kind,
                "reason": reason,
            }
            for before, after, kind, reason in result["transitions"]
        ],
    }
    if result["unresolved"]:
        summary["unresolved"] = result["unresolved"]
    if search.stats:
        summary["stats"] = search.stats
    if control:
        summary["control"] = control
    if "sequence" in kw:
        summary["skeleton"] = _masked_sequence(kw, retained)
    return summary


def _pass_rate(
    c: Controls, rule: str, alpha: float, replicates: int
) -> float | None:
    """Estimate the chance that a harmless deletion, scoring like the
    controls, passes `rule` under the `t` test; None under `rank`."""
    if c.flat:
        return 1.0
    if c.test != "t":
        return None
    q = t_quantile(1.0 - alpha, c.n - 1)
    sign = 1.0 if rule == "detectable_loss" else -1.0
    return NormalDist().cdf(c.margin / c.se(replicates) + sign * q)


def _stage(c: Controls, rule: str, alpha: float, replicates: int) -> dict:
    """Summarize a stage that judges a fixed number of replicates."""
    return {
        "rule": rule,
        "alpha": alpha,
        "replicates": replicates,
        "threshold": c.threshold(rule, alpha, replicates),
        "harmless_pass_rate": _pass_rate(c, rule, alpha, replicates),
    }


def _control_summary(
    c: Controls,
    reps: int,
    rules: dict,
    tally: Counter,
    sequential: SequentialTest | None,
) -> dict:
    """Summarize the controls and each stage's rule and thresholds."""
    info = c.summary()
    alpha = rules["alpha"]
    if not (rules["screened"] or sequential):
        if c.test != "mean":
            info["alpha"] = alpha
        threshold = c.threshold("detectable_loss", alpha, reps)
        if threshold is None:
            info["smallest_pvalue"] = 1.0 / math.comb(c.n + reps, reps)
        else:
            info["threshold"] = threshold
        return info
    stages = {}
    if rules["screened"]:
        stages["screen"] = _stage(
            c, "detectable_loss", rules["screen_alpha"], 1
        )
    for phase in ("search", "sweep"):
        rule = rules[f"{phase}_rule"]
        if rule in SEQUENTIAL_RULES:
            stages[phase] = sequential.summary(rule)
        elif rule is not None:
            stages[phase] = _stage(c, rule, alpha, reps)
    info["margin"] = c.margin
    info["stages"] = stages
    info["sweep"] = rules["sweep_rule"] is not None
    info["verdicts"] = dict(sorted(tally.items()))
    if sequential:
        info["error_rate"] = sequential.error_rate
    return info


def make_search_churn(
    search_class: type[KnockoutSearch], *, num_control_trials: int
) -> typing.Callable[[dict, list[dict], list[dict], list], list[dict]]:
    """Create a churn function that replays `search_class` as `search_churn`
    does.

    Parameters
    ----------
    search_class : type
        A `KnockoutSearch` subclass.
    num_control_trials : int
        How many times the wildtype runs, as the controls every genotype's
        scores are judged against.

    Returns
    -------
    Callable[[dict, list[dict], list[dict], list], list[dict]]
        The churn function, `churn(dispatch, trial_submissions,
        trial_payloads, memo)`.

    Raises
    ------
    ValueError
        If `num_control_trials` is not positive.
    """
    if int(num_control_trials) < 1:
        raise ValueError("num_control_trials must be positive")

    def churn(
        dispatch: dict,
        trial_submissions: list[dict],
        trial_payloads: list[dict],
        memo: list,
    ) -> list[dict]:
        return search_churn(
            search_class,
            dispatch,
            trial_submissions,
            trial_payloads,
            num_control_trials=int(num_control_trials),
        )

    return churn


def search_churn(
    search_class: type[KnockoutSearch],
    dispatch: dict,
    trial_submissions: list[dict],
    trial_payloads: list[dict],
    *,
    num_control_trials: int,
) -> list[dict]:
    """Decide what churn should do next by replaying `search_class` over
    the recorded trials.

    Every tick replays the search from the start, feeding it verdicts
    computed from recorded trials, until it asks about a genotype whose
    trials are not all in. Churn then launches the missing trials and
    returns; once the search ends, churn succeeds with its result. Nothing
    is memoized: the trial records are the state.

    Each phase has a rule: `search_rule` while the policy searches, and
    `sweep_rule` in the sweep and the final audit after it (None for no
    sweep). Either is `detectable_loss` (reject only a detectable loss) or
    `noninferiority` (accept only a loss shown to be within the margin). If
    either is `noninferiority`, a genotype's verdict comes in two stages:
    its replicate 0 screens it, rejecting a detectable loss, and replicates
    1 to `replicates` then confirm it by its phase's rule.

    A phase's rule may instead be sequential, `sprt` or `mixture` (see
    `SequentialTest`). Its genotypes are judged look by look: the first
    look takes `replicates` scores and each later one doubles the total,
    up to `max_replicates`, where an undecided genotype is rejected. The
    other phase's rule is then the same, `detectable_loss` or None.

    See docs/skeletonization.md for the assay kwargs.

    Parameters
    ----------
    search_class : type
        A `KnockoutSearch` subclass.
    dispatch : dict
        The dispatch record, with `assay_kwargs`.
    trial_submissions : list of dict
        The dispatch's trial submissions.
    trial_payloads : list of dict
        The dispatch's trial payloads.
    num_control_trials : int
        How many times the wildtype runs, as the controls every genotype's
        scores are judged against.

    Returns
    -------
    list of dict
        This step's actions.
    """
    trials = scd_churn.fold_trials(trial_submissions, trial_payloads)
    kw = dispatch["assay_kwargs"]
    n = len(kw["sequence"]) if "sequence" in kw else int(kw["n_sites"])
    reps = int(kw.get("replicates", 1))
    if reps < 1:
        raise ValueError("replicates must be positive")
    alpha = float(kw.get("alpha", 0.05))
    rules = {
        "search_rule": kw.get("search_rule", "detectable_loss"),
        "sweep_rule": kw.get("sweep_rule", "detectable_loss"),
        "alpha": alpha,
        "screen_alpha": float(kw.get("screen_alpha", alpha)),
    }
    known = (*RULES, *SEQUENTIAL_RULES)
    if rules["search_rule"] not in known:
        raise ValueError(f"search_rule must be one of {known}")
    if rules["sweep_rule"] not in (*known, None):
        raise ValueError(f"sweep_rule must be one of {known} or null")
    phase_rules = {rules["search_rule"], rules["sweep_rule"]} - {None}
    # with noninferiority anywhere, every genotype is screened, then
    # confirmed: one trial key layout for the whole dispatch
    rules["screened"] = screened = "noninferiority" in phase_rules
    streamed = phase_rules & set(SEQUENTIAL_RULES)
    if len(streamed) > 1 or (streamed and screened):
        raise ValueError(
            "a sequential rule goes with itself, detectable_loss or no sweep"
        )
    # a stream never reuses the replicates another rule has judged
    stream_start = reps if len(phase_rules) > 1 else 0
    search_kwargs = {
        k: kw[k]
        for k in (*SEARCH_KWARGS, *search_class.policy_kwargs)
        if k in kw
    }
    if phase_rules == streamed:
        # every commit passed within the error rate: a fresh audit would
        # only risk rejecting one again
        search_kwargs.setdefault("final_audit", False)
    # the search's own Random, replayed every tick: never the global one
    seed = kw.get("search_seed", dispatch["meta_seed"])
    search = search_class(
        range(n),
        batch_size=int(kw.get("batch_size", 8)),
        seed=seed,
        sweep=rules["sweep_rule"] is not None,
        rejudge_at_sweep=rules["sweep_rule"]
        not in (None, rules["search_rule"]),
        **search_kwargs,
    )
    wildtype = search.original
    by_key = {canonical_json(t["key"]): t for t in trials}
    missing, waiting = {}, 0  # the wave's trials yet to launch, or run

    def need(
        g: frozenset[int], fresh: int, replicates: typing.Iterable[int]
    ) -> list | None:
        """Collect the results of `g`'s `replicates`, noting the trials
        missing or still running; None until all are in."""
        nonlocal waiting
        found = []
        for rep in replicates:
            key = _trial_key(g, rep, fresh)
            t = by_key.get(canonical_json(key))
            if t is None:
                missing[canonical_json(key)] = {
                    "key": key,
                    "cmd": kw["cmd"],
                    "env": _trial_env(kw, n, g, rep),
                }
            elif t["state"] == "pending":
                waiting += 1
            else:
                found.append(t)
        if len(found) < len(replicates):
            return None
        return [scd_churn.trial_result(t) for t in found]

    # the Controls and any SequentialTest, once a score is first judged
    made: list = []
    tally: Counter = Counter()  # each phase's verdicts, where staged
    streams: dict = {}  # each sequential test's number, in the order asked

    def controls(baseline: list) -> tuple[Controls, SequentialTest | None]:
        if not made:
            scores = []
            for r in map(_as_dict, baseline):
                if "score" not in r:
                    raise ValueError(f"trial result lacks ['score']: {r!r}")
                scores.append(float(r["score"]))
            c = Controls(kw, scores)
            if screened and not c.flat and c.margin <= 0:
                raise ValueError(
                    "noninferiority needs a margin: set rel_tol or abs_tol"
                )
            sequential = SequentialTest(kw, c, n) if streamed else None
            if sequential and sequential.max_replicates < reps:
                raise ValueError("max_replicates must be at least replicates")
            # refuse settings no candidate could pass, before judging one
            _control_summary(c, reps, rules, tally, sequential)
            made.extend([c, sequential])
        return made[0], made[1]

    def judge(
        baseline: list, rule: str, alpha: float
    ) -> typing.Callable[[list[float]], str]:
        def verdict(scores: list[float]) -> str:
            c, _ = controls(baseline)
            return ACCEPT if c.accepts(scores, rule, alpha) else REJECT

        return verdict

    def follow_stream(
        g: frozenset[int], fresh: int, rule: str, phase: str, baseline: list
    ) -> str | None:
        """Judge `g` by a sequential rule, look by look; None until the
        next look's trials are in."""
        index = streams.setdefault((g, fresh), len(streams))

        def decide(scores: list[float]) -> str | None:
            _, sequential = controls(baseline)
            return sequential.judge(scores, rule, sequential.alpha(index))

        total = reps
        while True:
            results = need(g, fresh, range(stream_start, stream_start + total))
            if results is None or baseline is None:
                return None
            verdict = _verdict(kw, results, baseline, decide, scores_only=True)
            most = made[1].max_replicates if made else total
            if verdict is None and total < most:
                total = min(2 * total, most)
                continue
            tally[f"{phase}_{rule}_{verdict or 'capped'}"] += 1
            return verdict or REJECT

    def screen_then_confirm(
        g: frozenset[int],
        fresh: int,
        rule: str,
        phase: str,
        baseline: list | None,
    ) -> str | None:
        """Screen `g` on replicate 0 and, if it passes, confirm it by
        `rule` on replicates 1 to `replicates`; None until its trials are
        in."""
        first = need(g, fresh, [0])
        if first is None or baseline is None:
            return None
        screen = judge(baseline, "detectable_loss", rules["screen_alpha"])
        if _verdict(kw, first, baseline, screen, scores_only=True) == REJECT:
            tally[f"{phase}_screen_reject"] += 1
            return REJECT
        rest = need(g, fresh, range(1, reps + 1))
        if rest is None:
            return None
        confirm = judge(baseline, rule, alpha)
        verdict = _verdict(kw, rest, baseline, confirm, scores_only=True)
        tally[f"{phase}_{rule}_{verdict}"] += 1
        return verdict

    run = search.run()
    verdicts, waves = None, 0
    while True:
        try:
            wave = run.send(verdicts)
        except StopIteration as stop:
            control = (
                _control_summary(made[0], reps, rules, tally, made[1])
                if made
                else {}
            )
            summary = _summary(
                kw, search, stop.value, n, trials, waves, control
            )
            return [scd_churn.succeed(summary)]
        waves += 1
        fresh, sweeping = wave["fresh"], wave.get("sweep", False)
        phase = "sweep" if sweeping else "search"
        rule = rules["search_rule"]
        if sweeping and rules["sweep_rule"] is not None:
            rule = rules["sweep_rule"]  # without a sweep, the audit's
        missing, waiting = {}, 0
        # every wave also needs the wildtype's controls
        baseline = need(wildtype, 0, range(num_control_trials))
        verdicts = {}
        for g in wave["genotypes"]:
            if g == wildtype and not fresh:
                verdict = ACCEPT
            elif rule in SEQUENTIAL_RULES:
                verdict = follow_stream(g, fresh, rule, phase, baseline)
            elif screened:
                verdict = screen_then_confirm(g, fresh, rule, phase, baseline)
            else:
                verdict = None
                results = need(g, fresh, range(reps))
                if results is not None and baseline is not None:
                    verdict = _verdict(
                        kw, results, baseline, judge(baseline, rule, alpha)
                    )
                    if streamed:  # the other phase's rule is sequential
                        tally[f"{phase}_{rule}_{verdict}"] += 1
            if verdict is not None:
                verdicts[g] = verdict
        if missing or waiting:
            kept = len(search.current)
            message = (
                f"{search.policy}: {kept}/{n} sites retained, "
                f"{search.phase}, wave {waves}, "
                f"{waiting + len(missing)} trials outstanding"
            )
            launch = (
                [scd_churn.launch(list(missing.values()))] if missing else []
            )
            return [*launch, scd_churn.progress(n - kept, n, message)]
