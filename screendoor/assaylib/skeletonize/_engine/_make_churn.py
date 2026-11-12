"""Turn the replayable Search into a pure churn function.

Every tick replays the search from the start, feeding it verdicts computed
from recorded trials, until it asks about a genotype whose trials are not
all in. Churn launches the missing ones and returns. Nothing is memoized:
the trial records are the state.
"""

from .... import act
from ....auxlib import canonical_json
from ....rng._derive_seed import derive_seed
from ._codec import encode_sites
from ._search import ACCEPT, REJECT, Search

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
    key = {"g": encode_sites(g), "rep": rep}
    if fresh:
        key["fresh"] = fresh
    return key


def _trial_env(kw: dict, n: int, g: frozenset, rep: int) -> dict:
    env = {
        "retained": encode_sites(g),
        "knockout": encode_sites(frozenset(range(n)) - g),
        "n_sites": str(n),
        "replicate": str(rep),
        **kw.get("env", {}),
    }
    if "sequence" in kw:
        nop = kw.get("nop_symbol", "A")
        env["sequence"] = "".join(
            symbol if i in g else nop
            for i, symbol in enumerate(kw["sequence"])
        )
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
    if all("accept" in r for r in rs):
        fraction = sum(bool(r["accept"]) for r in rs) / len(rs)
        return ACCEPT if fraction >= kw.get("accept_fraction", 1.0) else REJECT
    if any(r.get("viable", True) is False for r in rs):
        return REJECT
    for field in kw.get("require_atleast", []):
        if any(
            got < want
            for r in rs
            for got, want in zip(r[field], baseline[0][field])
        ):
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
        summary["skeleton"] = _trial_env(kw, n, retained, 0)["sequence"]
    return summary


def make_churn(policy: str):
    def churn(dispatch, trials, memo, *, rng):
        kw = dispatch["assay_kwargs"]
        n = len(kw["sequence"]) if "sequence" in kw else int(kw["n_sites"])
        reps = int(kw.get("replicates", 1))
        seed = kw.get("search_seed")
        if seed is None:
            seed = derive_seed(dispatch["seed"], "skeletonize", policy)
        search = Search(
            range(n),
            policy=policy,
            batch_size=int(kw.get("batch_size", 8)),
            seed=seed,
            **{k: kw[k] for k in SEARCH_KWARGS if k in kw},
        )
        wildtype = search.original
        by_key = {canonical_json(t["key"]): t for t in trials}

        def lookup(g, fresh) -> dict:
            """Each replicate's trial key -> its trial, or None."""
            keys = [_trial_key(g, rep, fresh) for rep in range(reps)]
            return {
                canonical_json(k): by_key.get(canonical_json(k)) for k in keys
            }

        def results_of(g, fresh, *, required=False):
            """The replicates' results; None if a trial failed and the
            genotype is to be rejected for it."""
            found = lookup(g, fresh).values()
            # a null result: the trial failed, or its script sent none
            bad = next((t for t in found if t["result"] is None), None)
            if bad is None:
                return [t["result"] for t in found]
            if not required and kw.get("on_trial_failure", "fail") != "fail":
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
                    summary = _summary(
                        kw, search, stop.value, n, trials, waves
                    )
                    return [act.succeed(summary)]
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
                        f"{policy}: {kept}/{n} sites retained, "
                        f"{search.phase}, wave {waves}, "
                        f"{waiting + len(missing)} trials outstanding"
                    )
                    launch = (
                        [act.launch(list(missing.values()))] if missing else []
                    )
                    return [*launch, act.progress(n - kept, n, message)]
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
            return [act.fail(str(e))]

    churn.__doc__ = f"Skeletonize by knockout with the {policy!r} policy."
    return churn
