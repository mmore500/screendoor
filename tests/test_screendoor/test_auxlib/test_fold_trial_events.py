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
        "requested",
        attempt,
        key={"i": 1},
        request={"cmd": "x", "env": {}},
        job={"name": f"job{attempt}", "index": 0},
    )


def test_lifecycle():
    evs = [requested()]
    (t,) = fold_trial_events(evs)
    assert (t["status"], t["state"]) == ("requested", "pending")
    assert t["job"] == {"name": "job0", "index": 0}
    evs.append(ev("completed", result=3, channels={"telemetry": [1]}))
    (t,) = fold_trial_events(evs)
    assert t["status"] == "succeeded" and t["result"] == 3
    assert t["state"] == "complete"
    assert t["channels"] == {"telemetry": [1]}


def test_order_independent():
    evs = [
        requested(),
        requested(1),
        ev("failed", 1, exit_code=2),
    ]
    (want,) = fold_trial_events(evs)
    assert (want["status"], want["attempt"]) == ("failed", 1)
    assert (want["exit_code"], want["result"]) == (2, None)
    rng = random.Random(1)
    for _ in range(30):
        rng.shuffle(evs)
        assert fold_trial_events(evs) == [want]


def test_relaunched_is_requested_again():
    (t,) = fold_trial_events([requested(), requested(1)])
    assert (t["status"], t["attempt"]) == ("requested", 1)
    assert t["job"] == {"name": "job1", "index": 0}


def test_late_result_of_old_attempt_counts():
    evs = [
        requested(),
        requested(1),
        ev("completed", 0, result="late", channels={}),
    ]
    for perm in itertools.permutations(evs):
        assert fold_trial_events(list(perm))[0]["status"] == "succeeded"


def test_killed_attempt_is_not_a_failure():
    evs = [
        requested(),
        ev("killed"),
        ev("failed", exit_code=143),
    ]
    for perm in itertools.permutations(evs):
        (t,) = fold_trial_events(list(perm))
        assert (t["status"], t["kills"], t["exit_code"]) == ("killed", 1, None)
        assert t["state"] == "pending"
    (t,) = fold_trial_events([*evs, requested(1)])
    assert (t["status"], t["attempt"], t["kills"]) == ("requested", 1, 1)
    (t,) = fold_trial_events([*evs, ev("completed", result=1, channels={})])
    assert t["status"] == "succeeded"


def test_payload_without_request_is_ignored():
    assert fold_trial_events([ev("completed", result=1)]) == []
