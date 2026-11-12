"""Replay a KnockoutSearch as a pure churn function.

Every tick replays the search from the start, feeding it verdicts computed
from recorded trials, until it asks about a genotype whose trials are not
all in. Churn launches the missing ones and returns. Nothing is memoized:
the trial records are the state.
"""

from .... import churn as scd_churn
from ....auxlib import canonical_json
from ....auxlib._encode_sites import encode_sites
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


class _Fail(Exception):
    """Fails the dispatch with this reason."""


def _trial_key(g: frozenset, rep: int, fresh: int) -> dict:
    key = {"retained": encode_sites(g), "replicate": rep}
    if fresh:
        key["fresh"] = fresh
    return key


def _masked_sequence(kw: dict, g: frozenset) -> str:
    nop = kw.get("nop_symbol", "A")
    return "".join(s if i in g else nop for i, s in enumerate(kw["sequence"]))


def _trial_env(kw: dict, n: int, g: frozenset, rep: int) -> dict:
    """The user's ``env``, then the assay's variables, which win."""
    env = {
        **kw.get("env", {}),
        "retained": encode_sites(g),
        "knockout": encode_sites(frozenset(range(n)) - g),
        "n_sites": str(n),
        "replicate": str(rep),
    }
    if "sequence" in kw:
        env["sequence"] = _masked_sequence(kw, g)
    return env


def _as_dict(result) -> dict:
    if isinstance(result, bool):
        return {"accept": result}
    if isinstance(result, (int, float)):
        return {"score": float(result)}
    if isinstance(result, dict):
        return result
    raise _Fail(f"trial result must be a bool, number or object: {result!r}")


def _verdict(kw: dict, results: list, baseline: list) -> str:
    """Accept or reject a genotype from its replicates' results."""
    rs = [_as_dict(r) for r in results]
    baseline = [_as_dict(b) for b in baseline]
    if any("accept" in r for r in rs):
        if not all("accept" in r for r in rs):
            raise _Fail("some results have 'accept' and some do not")
        fraction = sum(bool(r["accept"]) for r in rs) / len(rs)
        return ACCEPT if fraction >= kw.get("accept_fraction", 1.0) else REJECT
    if any(r.get("viable", True) is False for r in rs):
        return REJECT
    for r in [*rs, *baseline]:
        missing = [
            f for f in ("score", *kw.get("require_atleast", ())) if f not in r
        ]
        if missing:
            raise _Fail(f"trial result lacks {missing}: {r!r}")
    for field in kw.get("require_atleast", []):
        want = baseline[0][field]
        for r in rs:
            if len(r[field]) != len(want):
                raise _Fail(
                    f"{field!r} has {len(r[field])} entries, not {len(want)}"
                )
            if any(g < w for g, w in zip(r[field], want)):
                return REJECT
    score = sum(float(r["score"]) for r in rs) / len(rs)
    base = sum(float(b["score"]) for b in baseline) / len(baseline)
    threshold = base * (1.0 - kw.get("rel_tol", 0.0)) - kw.get("abs_tol", 0.0)
    return ACCEPT if score >= threshold - 1e-12 else REJECT


def _summary(kw, search, result, n, trials, waves) -> dict:
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
    if "sequence" in kw:
        summary["skeleton"] = _masked_sequence(kw, retained)
    return summary


def search_churn(search_class, dispatch, trial_submissions, trial_payloads):
    """What churn should do next, by replaying ``search_class`` (a
    KnockoutSearch) over the recorded trials: launch the next wave's
    missing trials, or succeed with the search's result."""
    trials = scd_churn.fold_trials(trial_submissions, trial_payloads)
    kw = dispatch["assay_kwargs"]
    n = len(kw["sequence"]) if "sequence" in kw else int(kw["n_sites"])
    reps = int(kw.get("replicates", 1))
    # the search's own Random, replayed every tick: never the global one
    seed = kw.get("search_seed", dispatch["meta_seed"])
    search = search_class(
        range(n),
        batch_size=int(kw.get("batch_size", 8)),
        seed=seed,
        **{k: kw[k] for k in SEARCH_KWARGS if k in kw},
    )
    wildtype = search.original
    by_key = {canonical_json(t["key"]): t for t in trials}

    def lookup(g, fresh) -> dict:
        """Each replicate's trial key -> its trial, or None."""
        keys = [_trial_key(g, rep, fresh) for rep in range(reps)]
        return {canonical_json(k): by_key.get(canonical_json(k)) for k in keys}

    def results_of(g, fresh, *, required=False):
        """The replicates' results; None if a trial failed and the
        genotype is to be rejected for it."""
        found = lookup(g, fresh).values()
        # a null result: the trial failed, or its script sent none
        bad = next((t for t in found if t["result"] is None), None)
        if bad is None:
            return [t["result"] for t in found]
        on_failure = kw.get("on_trial_failure", "fail")
        if on_failure not in ("fail", "reject"):
            raise _Fail(
                f"on_trial_failure must be fail or reject: {on_failure!r}"
            )
        if not required and on_failure == "reject":
            return None
        error = bad["error"] or {"kind": "no result"}
        raise _Fail(
            f"trial {bad['trial_uuid'][:8]} ({bad['key']}) failed: "
            f"{error['kind']} {error.get('exit_code', '')} "
            f"{(error.get('stderr_tail') or '')[-300:]}"
        )

    run = search.run()
    verdicts, waves = None, 0
    try:
        while True:
            try:
                wave = run.send(verdicts)
            except StopIteration as stop:
                summary = _summary(kw, search, stop.value, n, trials, waves)
                return [scd_churn.succeed(summary)]
            waves += 1
            fresh = wave["fresh"]
            # every wave also needs the fixed wildtype reference
            wanted = [
                *((g, fresh) for g in wave["genotypes"]),
                (wildtype, 0),
            ]
            missing, waiting = {}, 0
            for g, f in wanted:
                for rep, (key, t) in enumerate(lookup(g, f).items()):
                    if t is None:
                        missing[key] = {
                            "key": _trial_key(g, rep, f),
                            "cmd": kw["cmd"],
                            "env": _trial_env(kw, n, g, rep),
                        }
                    elif t["state"] == "pending":
                        waiting += 1
            if missing or waiting:
                kept = len(search.current)
                message = (
                    f"{search.policy}: {kept}/{n} sites retained, "
                    f"{search.phase}, wave {waves}, "
                    f"{waiting + len(missing)} trials outstanding"
                )
                launch = (
                    [scd_churn.launch(list(missing.values()))]
                    if missing
                    else []
                )
                return [*launch, scd_churn.progress(n - kept, n, message)]
            baseline = results_of(wildtype, 0, required=True)
            verdicts = {}
            for g in wave["genotypes"]:
                results = results_of(g, fresh)
                if results is None:
                    verdicts[g] = REJECT
                elif g == wildtype and not fresh:
                    verdicts[g] = ACCEPT
                else:
                    verdicts[g] = _verdict(kw, results, baseline)
    except _Fail as e:
        return [scd_churn.fail(str(e))]
