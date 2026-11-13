def tally_trials(trials: list[dict]) -> dict:
    """Count what happened across folded trials.

    Parameters
    ----------
    trials : list of dict
        Folded trials, as from `scd.churn.fold_trials`.

    Returns
    -------
    dict
        Counts of `trials`, `succeeded`, `failed`, `retries` (relaunches
        after a job vanished), `kills` (attempts cancelled by
        `kill_dispatch`) and `warnings` (values sent on the `warning`
        channel).
    """
    return {
        "trials": len(trials),
        "succeeded": sum(t["status"] == "succeeded" for t in trials),
        "failed": sum(t["status"] == "failed" for t in trials),
        "retries": sum(t["retries"] for t in trials),
        "kills": sum(t["kills"] for t in trials),
        "warnings": sum(len(t["channels"].get("warning", ())) for t in trials),
    }
