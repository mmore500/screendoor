def _attempt(event: dict) -> int:
    return event.get("attempt", 0)


def _fold_trial(trial_uuid: str, events: list[dict]) -> dict | None:
    requests = [e for e in events if e["event"] == "requested"]
    if not requests:
        return None  # payloads whose submission was torn
    first = min(requests, key=_attempt)
    latest = max(requests, key=_attempt)
    attempt = _attempt(latest)
    killed = {_attempt(e) for e in events if e["event"] == "killed"}
    trial = {
        "trial_uuid": trial_uuid,
        "task_id": first.get("task_id"),  # 0, 1, 2, ... in request order
        "key": first["key"],
        "request": first["request"],
        "status": "killed" if attempt in killed else "requested",
        "attempt": attempt,
        "job": latest.get("job"),  # {"name", "index"}: where it runs
        "result": None,
        "channels": {},
        "exit_code": None,
        "kills": len(killed),  # attempts cancelled by kill_dispatch
        "retries": 0,  # relaunches after a job vanished unkilled
    }
    done = max(
        (
            e
            for e in events
            if e["event"] == "completed"
            # a killed attempt's failure is the kill's doing, not a result
            or (e["event"] == "failed" and _attempt(e) not in killed)
        ),
        key=lambda e: (e["event"] == "completed", _attempt(e)),
        default=None,
    )
    if done is not None:
        trial.update(
            status="succeeded" if done["event"] == "completed" else "failed",
            attempt=max(attempt, _attempt(done)),
            result=done.get("result"),
            channels=done.get("channels", {}),
            exit_code=done.get("exit_code"),
        )
    succeeded_or_failed = trial["status"] in ("succeeded", "failed")
    trial["state"] = "complete" if succeeded_or_failed else "pending"
    relaunched_kills = sum(k < trial["attempt"] for k in killed)
    trial["retries"] = trial["attempt"] - relaunched_kills
    return trial


def fold_trial_events(events: list[dict]) -> list[dict]:
    """Fold trial submissions and payloads into one dict per trial, in
    order of first request; see scd.churn.fold_trials.

    Parameters
    ----------
    events : list of dict
        Trial submissions and payloads, in any order; records without
        ``trial_uuid`` are skipped.

    Returns
    -------
    list of dict
        The folded trials; a trial never requested is left out.
    """
    by_uuid: dict[str, list] = {}
    for ev in events:
        if "trial_uuid" in ev:
            by_uuid.setdefault(ev["trial_uuid"], []).append(ev)
    first_ts = {
        uid: min(
            (e["ts"] for e in evs if e["event"] == "requested"), default=""
        )
        for uid, evs in by_uuid.items()
    }
    trials = [_fold_trial(uid, evs) for uid, evs in by_uuid.items()]
    return sorted(
        filter(None, trials),
        key=lambda t: (first_ts[t["trial_uuid"]], t["trial_uuid"]),
    )
