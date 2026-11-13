from .... import churn as scd_churn
from ....auxlib._canonical_json import canonical_json
from ..._accepted import accepted


def churn(
    dispatch: dict,
    trial_submissions: list[dict],
    trial_payloads: list[dict],
    memo: list[dict],
) -> list[dict]:
    """Pull removable components one at a time, like Jenga blocks.

    Each round tries removing each of up to `batch_size` candidate
    components alone from those kept. The first whose removal passes is
    removed; if none passes, they are all marked load-bearing. The search's
    state is memoed from round to round, and the dispatch succeeds with the
    components `retained` once no candidate is left.

    `assay_kwargs`: `components` (names), `batch_size` (removals tried per
    round, default 8), `cmd` and `env`. Each trial gets `$components`, the
    kept components less the one removed, and passes (the removal is
    harmless) if it sends `true` or `{"accept": true}`; churn raises on a
    trial with no result.

    Parameters
    ----------
    dispatch : dict
        The dispatch record, with `assay_kwargs`.
    trial_submissions : list of dict
        The dispatch's trial submissions.
    trial_payloads : list of dict
        The dispatch's trial payloads.
    memo : list of dict
        The memo payloads, oldest first; the last is the search's state.

    Returns
    -------
    list of dict
        This step's actions.
    """
    trials = scd_churn.fold_trials(trial_submissions, trial_payloads)
    kw = dispatch["assay_kwargs"]
    state = (
        memo[-1]
        if memo
        else {"round": 0, "kept": kw["components"], "load_bearing": []}
    )
    round_ = state["round"]
    candidates = [c for c in state["kept"] if c not in state["load_bearing"]]
    candidates = candidates[: kw.get("batch_size", 8)]
    if not candidates:
        return [
            scd_churn.succeed({"retained": state["kept"], "rounds": round_})
        ]

    by_key = {canonical_json(t["key"]): t for t in trials}
    this_round = {
        c: by_key.get(canonical_json({"round": round_, "remove": c}))
        for c in candidates
    }
    progress = scd_churn.progress(
        round_, round_ + len(candidates), f"round {round_}"
    )
    missing = [c for c, t in this_round.items() if t is None]
    if missing:
        return [
            scd_churn.launch(
                [
                    {
                        "key": {"round": round_, "remove": c},
                        "cmd": kw["cmd"],
                        "env": {
                            **kw.get("env", {}),
                            "components": " ".join(
                                k for k in state["kept"] if k != c
                            ),
                        },
                    }
                    for c in missing
                ]
            ),
            progress,
        ]
    if any(t["state"] == "pending" for t in this_round.values()):
        return [progress]

    passing = [
        c
        for c in candidates
        if accepted(scd_churn.trial_result(this_round[c]))
    ]
    if passing:
        kept = [k for k in state["kept"] if k != passing[0]]
        next_state = {**state, "kept": kept}
    else:
        load_bearing = state["load_bearing"] + candidates
        next_state = {**state, "load_bearing": load_bearing}
    return [scd_churn.memo({**next_state, "round": round_ + 1})]
