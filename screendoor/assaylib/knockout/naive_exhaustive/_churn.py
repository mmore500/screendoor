from .... import act
from ....auxlib import canonical_json


def churn(dispatch, trials, memo, *, rng):
    """Knock out every target plus a baseline; report big score drops."""
    kw = dispatch["assay_kwargs"]
    arms = [None, *kw["targets"]]  # None = baseline (no knockout)
    # keys are dicts, so look trials up by their canonical JSON
    by_key = {canonical_json(t["key"]): t for t in trials}
    by_arm = {a: by_key.get(canonical_json({"knockout": a})) for a in arms}

    actions = []
    missing = [a for a, t in by_arm.items() if t is None]
    if missing:
        actions.append(
            act.launch(
                [
                    {
                        "key": {"knockout": a},
                        "cmd": kw["cmd"],
                        "env": {"knockout": a or ""},
                    }
                    for a in missing
                ]
            )
        )
    done = [t for t in by_arm.values() if t and t["state"] == "complete"]
    if len(done) < len(by_arm):
        return actions + [act.progress(len(done), len(by_arm))]

    # a null result means the script sent none: count it as failed
    failed = [a for a, t in by_arm.items() if t["result"] is None]
    if None in failed:
        return [act.fail("baseline trial failed")]
    base = by_arm[None]["result"]["score"]
    if len(failed) > kw.get("max_failed", 0):
        return [act.fail(f"{len(failed)} trials failed")]
    hits = [
        a
        for a, t in by_arm.items()
        if a is not None
        and a not in failed
        and base - t["result"]["score"] > kw["threshold"]
    ]
    return [act.succeed({"baseline": base, "hits": hits, "failed": failed})]
