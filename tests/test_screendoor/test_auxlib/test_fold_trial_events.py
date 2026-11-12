import itertools
import random

from screendoor.auxlib._fold_trial_events import fold_trial_events


def ev(event, attempt=0, **fields):
    return {
        "event": event,
        "trial_uuid": "u",
        "attempt": attempt,
        "ts": "2026-11-11T00:00:00+00:00",
        **fields,
    }


def requested(attempt=0):
    return ev(
        "requested", attempt, key={"i": 1}, request={"cmd": "x", "env": {}}
    )


def test_lifecycle():
    evs = [requested()]
    assert fold_trial_events(evs)[0]["status"] == "requested"
    evs.append(ev("launched", job_id="7"))
    assert fold_trial_events(evs)[0]["status"] == "launched"
    evs.append(ev("started"))
    (t,) = fold_trial_events(evs)
    assert (t["status"], t["state"]) == ("running", "pending")
    evs.append(ev("completed", result=3, channels={"telemetry": [1]}))
    (t,) = fold_trial_events(evs)
    assert t["status"] == "succeeded" and t["result"] == 3
    assert t["state"] == "complete"
    assert t["channels"] == {"telemetry": [1]}
    assert t["job_id"] == "7"


def test_order_independent():
    evs = [
        requested(),
        ev("launched", job_id="7"),
        ev("started"),
        requested(1),
        ev("launched", 1, job_id="8"),
        ev("started", 1),
        ev("failed", 1, kind="error", exit_code=2, stderr_tail="boom"),
    ]
    (want,) = fold_trial_events(evs)
    assert (want["status"], want["attempt"]) == ("failed", 1)
    assert want["error"]["kind"] == "error"
    rng = random.Random(1)
    for _ in range(30):
        rng.shuffle(evs)
        assert fold_trial_events(evs) == [want]


def test_relaunched_is_requested_again():
    evs = [requested(), ev("launched", job_id="7"), requested(1)]
    (t,) = fold_trial_events(evs)
    assert (t["status"], t["attempt"], t["job_id"]) == ("requested", 1, None)


def test_late_result_of_old_attempt_counts():
    evs = [
        requested(),
        ev("launched", job_id="7"),
        requested(1),
        ev("completed", 0, result="late", channels={}),
    ]
    for perm in itertools.permutations(evs):
        assert fold_trial_events(list(perm))[0]["status"] == "succeeded"


def test_killed_attempt_is_not_a_failure():
    evs = [
        requested(),
        ev("launched", job_id="7"),
        ev("killed", job_id="7"),
        ev("failed", kind="error", exit_code=143, stderr_tail=""),
    ]
    for perm in itertools.permutations(evs):
        (t,) = fold_trial_events(list(perm))
        assert (t["status"], t["kills"], t["error"]) == ("killed", 1, None)
        assert t["state"] == "pending"
    (t,) = fold_trial_events([*evs, requested(1)])
    assert (t["status"], t["attempt"], t["kills"]) == ("requested", 1, 1)
    (t,) = fold_trial_events([*evs, ev("completed", result=1, channels={})])
    assert t["status"] == "succeeded"


def test_lifecycle_without_request_is_ignored():
    assert fold_trial_events([ev("started")]) == []
