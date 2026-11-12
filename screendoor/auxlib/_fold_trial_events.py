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
        "error": None,
        "kills": len(killed),  # attempts cancelled by kill_dispatch
        "retries": 0,  # relaunches after a job vanished unkilled
        "malformed": 0,
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
        trial["attempt"] = max(attempt, _attempt(done))
        trial["channels"] = done.get("channels", {})
        trial["malformed"] = done.get("malformed", 0)
        if done["event"] == "completed":
            trial.update(status="succeeded", result=done.get("result"))
        else:
            keys = ("kind", "exit_code", "stderr_tail")
            trial.update(status="failed", error={k: done.get(k) for k in keys})
    done_statuses = ("succeeded", "failed")
    trial["state"] = (
        "complete" if trial["status"] in done_statuses else "pending"
    )
    relaunched_kills = sum(k < trial["attempt"] for k in killed)
    trial["retries"] = trial["attempt"] - relaunched_kills
    return trial


def fold_trial_events(events: list[dict]) -> list[dict]:
    """Fold trial submissions and payloads into trial dicts, whatever the
    line order.

    Submissions are ``requested`` (one per attempt, naming the job that
    runs it) and ``killed``; payloads are ``completed`` and ``failed``. A
    payload from any attempt settles the trial, ``completed`` over
    ``failed``. Until then a trial is ``requested``, or ``killed`` if
    kill_dispatch cancelled its newest attempt. Each trial's ``state`` is
    ``complete`` once it has succeeded or failed, and ``pending``
    otherwise. Trials are ordered by first request.
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
