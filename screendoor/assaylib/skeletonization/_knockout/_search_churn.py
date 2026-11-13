from collections import Counter
import math
from statistics import NormalDist
import typing

from .... import churn as scd_churn
from ....auxlib._canonical_json import canonical_json
from ....auxlib._encode_sites import encode_sites
from ._KnockoutSearch import KnockoutSearch
from ._controls import RULES, Controls, t_quantile
from ._masks import ACCEPT, REJECT

SEARCH_KWARGS = (
    "combination_rounds",
    "exact",
    "final_audit",
    "audit_every",
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
    judge: typing.Callable[[list[float]], bool],
    *,
    scores_only: bool = False,
) -> str:
    """Accept or reject a genotype from its replicates' results, given the
    wildtype controls' results, `baseline`.

    `judge(scores)` judges the replicates' scores; `scores_only` refuses
    `accept` results.
    """
    rs = [_as_dict(r) for r in results]
    baseline = [_as_dict(b) for b in baseline]
    if scores_only and any("accept" in r for r in rs):
        raise ValueError("noninferiority needs scores, not accept results")
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
    return ACCEPT if judge([float(r["score"]) for r in rs]) else REJECT


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


def _control_summary(
    c: Controls, reps: int, rules: dict, tally: Counter
) -> dict:
    """Summarize the controls and each stage's rule, alpha and
    threshold."""
    info = c.summary()
    if not rules["sequential"]:
        alpha = rules["alpha"]
        if c.test != "mean":
            info["alpha"] = alpha
        threshold = c.threshold("detectable_loss", alpha, reps)
        if threshold is None:
            info["smallest_pvalue"] = 1.0 / math.comb(c.n + reps, reps)
        else:
            info["threshold"] = threshold
        return info
    stages = {
        "screen": ("detectable_loss", rules["screen_alpha"], 1),
        "search": (rules["search_rule"], rules["alpha"], reps),
    }
    if rules["sweep_rule"] is not None:
        stages["sweep"] = (rules["sweep_rule"], rules["alpha"], reps)
    info["margin"] = c.margin
    info["stages"] = {
        name: {
            "rule": rule,
            "alpha": alpha,
            "replicates": r,
            "threshold": c.threshold(rule, alpha, r),
            "harmless_pass_rate": _pass_rate(c, rule, alpha, r),
        }
        for name, (rule, alpha, r) in stages.items()
    }
    info["sweep"] = rules["sweep_rule"] is not None
    info["verdicts"] = dict(sorted(tally.items()))
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
    if rules["search_rule"] not in RULES:
        raise ValueError(f"search_rule must be one of {RULES}")
    if rules["sweep_rule"] not in (*RULES, None):
        raise ValueError(f"sweep_rule must be one of {RULES} or null")
    # with noninferiority anywhere, every genotype is screened, then
    # confirmed: one trial key layout for the whole dispatch
    rules["sequential"] = sequential = "noninferiority" in (
        rules["search_rule"],
        rules["sweep_rule"],
    )
    # the search's own Random, replayed every tick: never the global one
    seed = kw.get("search_seed", dispatch["meta_seed"])
    search = search_class(
        range(n),
        batch_size=int(kw.get("batch_size", 8)),
        seed=seed,
        sweep=rules["sweep_rule"] is not None,
        rejudge_at_sweep=rules["sweep_rule"]
        not in (None, rules["search_rule"]),
        **{
            k: kw[k]
            for k in (*SEARCH_KWARGS, *search_class.policy_kwargs)
            if k in kw
        },
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

    made: list[Controls] = []  # the Controls, once a score is first judged
    tally: Counter = Counter()  # screened and confirmed verdicts, by phase

    def controls(baseline: list) -> Controls:
        if not made:
            scores = []
            for r in map(_as_dict, baseline):
                if "score" not in r:
                    raise ValueError(f"trial result lacks ['score']: {r!r}")
                scores.append(float(r["score"]))
            c = Controls(kw, scores)
            if sequential and not c.flat and c.margin <= 0:
                raise ValueError(
                    "noninferiority needs a margin: set rel_tol or abs_tol"
                )
            # refuse settings no candidate could pass, before judging one
            _control_summary(c, reps, rules, tally)
            made.append(c)
        return made[0]

    def judge(
        baseline: list, rule: str, alpha: float
    ) -> typing.Callable[[list[float]], bool]:
        return lambda scores: controls(baseline).accepts(scores, rule, alpha)

    def screen_then_confirm(
        g: frozenset[int], fresh: int, sweeping: bool, baseline: list | None
    ) -> str | None:
        """Screen `g` on replicate 0 and, if it passes, confirm it on
        replicates 1 to `replicates`; None until its trials are in."""
        phase = "sweep" if sweeping else "search"
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
        rule = rules["search_rule"]
        if sweeping and rules["sweep_rule"] is not None:
            rule = rules["sweep_rule"]  # without a sweep, the audit's
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
                _control_summary(made[0], reps, rules, tally) if made else {}
            )
            summary = _summary(
                kw, search, stop.value, n, trials, waves, control
            )
            return [scd_churn.succeed(summary)]
        waves += 1
        fresh, sweeping = wave["fresh"], wave.get("sweep", False)
        missing, waiting = {}, 0
        # every wave also needs the wildtype's controls
        baseline = need(wildtype, 0, range(num_control_trials))
        verdicts = {}
        for g in wave["genotypes"]:
            if g == wildtype and not fresh:
                verdicts[g] = ACCEPT
            elif not sequential:
                results = need(g, fresh, range(reps))
                if results is not None and baseline is not None:
                    rule = judge(baseline, "detectable_loss", alpha)
                    verdicts[g] = _verdict(kw, results, baseline, rule)
            else:
                verdict = screen_then_confirm(g, fresh, sweeping, baseline)
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
