def tally_trials(trials: list[dict]) -> dict:
    """Count what happened across folded trials.

    ``retries`` are relaunches after a job vanished. ``kills`` are
    attempts cancelled by kill_dispatch. ``warnings`` are values trials
    sent on the ``warning`` channel.
    """
    return {
        "trials": len(trials),
        "succeeded": sum(t["status"] == "succeeded" for t in trials),
        "failed": sum(t["status"] == "failed" for t in trials),
        "retries": sum(t["retries"] for t in trials),
        "kills": sum(t["kills"] for t in trials),
        "warnings": sum(len(t["channels"].get("warning", ())) for t in trials),
    }
