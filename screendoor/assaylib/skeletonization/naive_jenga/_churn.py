from .... import churn as scd_churn
from ....auxlib import canonical_json


def churn(dispatch, trial_submissions, trial_payloads, memo):
    """Pull removable components one at a time, like Jenga blocks."""
    trials = scd_churn.fold_trials(trial_submissions, trial_payloads)
    kw = dispatch["assay_kwargs"]
    s = (
        memo[-1]
        if memo
        else {"round": 0, "kept": kw["components"], "load_bearing": []}
    )
    r = s["round"]
    candidates = [c for c in s["kept"] if c not in s["load_bearing"]][
        : kw.get("width", 8)
    ]
    if not candidates:
        return [scd_churn.succeed({"skeleton": s["kept"], "rounds": r})]

    # keys are dicts, so look trials up by their canonical JSON
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
                            "components": " ".join(
                                k for k in s["kept"] if k != c
                            )
                        },
                    }
                    for c in missing
                ]
            )
        ]
    if any(t["state"] == "pending" for t in this_round.values()):
        return []  # nothing new: wait for the round

    passing = [
        c
        for c in candidates
        if (this_round[c]["result"] or {}).get("passes")  # null: no result
    ]
    if passing:
        nxt = {**s, "kept": [k for k in s["kept"] if k != passing[0]]}
    else:
        nxt = {**s, "load_bearing": s["load_bearing"] + candidates}
    return [scd_churn.memo({**nxt, "round": r + 1})]
