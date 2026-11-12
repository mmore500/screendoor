from .... import churn as scd_churn
from ....auxlib import canonical_json
from ..._accepted import accepted


def churn(dispatch, trial_submissions, trial_payloads, memo):
    """Pull removable components one at a time, like Jenga blocks.

    ``assay_kwargs``: ``components`` (names), ``batch_size`` (removals
    tried per round, default 8), ``cmd`` and ``env``. Each trial gets
    ``$components``, the kept components less the one removed, and passes
    (the removal is harmless) if it sends ``true`` or ``{"accept": true}``;
    a failed trial or a null result counts as not passing.
    """
    trials = scd_churn.fold_trials(trial_submissions, trial_payloads)
    kw = dispatch["assay_kwargs"]
    s = (
        memo[-1]
        if memo
        else {"round": 0, "kept": kw["components"], "load_bearing": []}
    )
    r = s["round"]
    candidates = [c for c in s["kept"] if c not in s["load_bearing"]]
    candidates = candidates[: kw.get("batch_size", 8)]
    if not candidates:
        return [scd_churn.succeed({"retained": s["kept"], "rounds": r})]

    by_key = {canonical_json(t["key"]): t for t in trials}
    this_round = {
        c: by_key.get(canonical_json({"round": r, "remove": c}))
        for c in candidates
    }
    missing = [c for c, t in this_round.items() if t is None]
    if missing:
        return [
            scd_churn.launch(
                [
                    {
                        "key": {"round": r, "remove": c},
                        "cmd": kw["cmd"],
                        "env": {
                            **kw.get("env", {}),
                            "components": " ".join(
                                k for k in s["kept"] if k != c
                            ),
                        },
                    }
                    for c in missing
                ]
            ),
            scd_churn.progress(r, r + len(candidates), f"round {r}"),
        ]
    if any(t["state"] == "pending" for t in this_round.values()):
        return [scd_churn.progress(r, r + len(candidates), f"round {r}")]

    passing = [c for c in candidates if accepted(this_round[c]["result"])]
    if passing:
        nxt = {**s, "kept": [k for k in s["kept"] if k != passing[0]]}
    else:
        nxt = {**s, "load_bearing": s["load_bearing"] + candidates}
    return [scd_churn.memo({**nxt, "round": r + 1})]
