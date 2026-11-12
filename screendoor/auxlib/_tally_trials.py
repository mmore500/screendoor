def tally_trials(trials: list[dict]) -> dict:
    """Count what happened across folded trials.

    ``no_result`` are trials that succeeded without sending a result, so
    their result is null. ``retries`` are relaunches after a job vanished.
    ``kills`` are attempts cancelled by kill_dispatch. ``warnings`` are
    values trials sent on the ``warning`` channel. ``malformed`` are tagged
    lines that did not parse.
    """
    return {
        "trials": len(trials),
        "succeeded": sum(t["status"] == "succeeded" for t in trials),
        "failed": sum(t["status"] == "failed" for t in trials),
        "no_result": sum(
            t["status"] == "succeeded" and t["result"] is None for t in trials
        ),
        "retries": sum(t["retries"] for t in trials),
        "kills": sum(t["kills"] for t in trials),
        "warnings": sum(len(t["channels"].get("warning", ())) for t in trials),
        "malformed": sum(t["malformed"] for t in trials),
    }
