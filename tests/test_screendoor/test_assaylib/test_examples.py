import random

from screendoor.assaylib.potentiation.naive_scan import churn as scan_churn
from screendoor.assaylib.testing.exercise import churn as ex_churn
from screendoor.testing import simulate_dispatch

RNG = random.Random(0)


TS = "2026-11-11T00:00:00+00:00"


def trial(key, status="succeeded", result=None):
    """One trial's raw records: its submission and, unless still running,
    its payload."""
    base = {"trial_uuid": str(key), "attempt": 0, "ts": TS}
    sub = {**base, "event": "requested", "key": key, "request": {}}
    if status == "running":
        return [sub], []
    if status == "succeeded":
        pay = {**base, "event": "completed", "result": result, "channels": {}}
    else:
        pay = {**base, "event": "failed", "kind": "error", "channels": {}}
    return [sub], [pay]


def records(*trials):
    """``(trial_submissions, trial_payloads)`` for churn."""
    return (
        [e for subs, _ in trials for e in subs],
        [e for _, pays in trials for e in pays],
    )


def kinds(actions):
    return [a["action"] for a in actions]


def scan(timepoint, replicate, status="succeeded", result=None):
    key = {"timepoint": timepoint, "replicate": replicate}
    return trial(key, status, result)


SCAN = {
    "assay_kwargs": {"timepoints": [10, 20, 30], "replicates": 2, "cmd": "x"}
}


def test_naive_scan_one_timepoint_at_a_time():
    launch, progress = scan_churn(SCAN, [], [], [])
    assert kinds([launch, progress]) == ["launch", "progress"]
    trials = launch["kwargs"]["trials"]
    assert [t["key"] for t in trials] == [
        {"timepoint": 10, "replicate": 0},
        {"timepoint": 10, "replicate": 1},
    ]
    assert trials[1]["env"] == {
        "timepoint": "10",
        "timepoint_index": "0",
        "replicate": "1",
    }
    pending = [scan(10, 0, result=False), scan(10, 1, "running")]
    assert kinds(scan_churn(SCAN, *records(*pending), [])) == ["progress"]
    none = [scan(10, 0, result=False), scan(10, 1, result={"accept": False})]
    launch, _ = scan_churn(SCAN, *records(*none), [])
    assert {t["key"]["timepoint"] for t in launch["kwargs"]["trials"]} == {20}


def test_naive_scan_stops_at_first_success():
    trials = [
        scan(10, 0, result=False),
        scan(10, 1, result=False),
        scan(20, 0, result=False),
        scan(20, 1, result={"accept": True, "generations": 900}),
    ]
    (a,) = scan_churn(SCAN, *records(*trials), [])
    assert a["action"] == "succeed"
    summary = a["kwargs"]["summary"]
    assert (summary["timepoint"], summary["index"]) == (20, 1)
    assert [row["successes"] for row in summary["scanned"]] == [0, 1]


def test_naive_scan_without_success():
    trials = [
        scan(tp, r, result=False) for tp in (10, 20, 30) for r in range(2)
    ]
    (a,) = scan_churn(SCAN, *records(*trials), [])
    summary = a["kwargs"]["summary"]
    assert (summary["timepoint"], summary["index"]) == (None, None)
    assert len(summary["scanned"]) == 3


def test_naive_scan_failures():
    trials = [scan(10, 0, result=False), scan(10, 1, "failed")]
    assert kinds(scan_churn(SCAN, *records(*trials), [])) == ["fail"]
    tolerant = {"assay_kwargs": {**SCAN["assay_kwargs"], "max_failed": 1}}
    trials[1] = scan(10, 1)  # succeeded, but sent no result
    launch, _ = scan_churn(tolerant, *records(*trials), [])
    assert launch["action"] == "launch"  # counted as no success; next one


def test_naive_scan_simulated():
    r = simulate_dispatch(
        "scd.assaylib.potentiation.naive_scan",
        {
            "timepoints": [f"gen{g}" for g in range(0, 1000, 100)],
            "replicates": 3,
            "cmd": "x",
        },
        fake_trial=lambda t: {
            "accept": t["env"]["timepoint"] >= "gen600"
            and t["env"]["replicate"] == "2"
        },
    )
    summary = r["completed"]["summary"]
    assert (summary["timepoint"], summary["index"]) == ("gen600", 6)
    assert len(r["trials"]) == 7 * 3  # nothing past the first success


def test_jenga_simulated():
    r = simulate_dispatch(
        "scd.assaylib.skeletonization.jenga",
        {"components": list("abcdefgh"), "cmd": "x", "batch_size": 3},
        fake_trial=lambda t: {
            "accept": {"b", "g"} <= set(t["env"]["components"].split())
        },
    )
    assert r["completed"]["outcome"] == "succeeded"
    assert r["completed"]["summary"]["retained"] == ["b", "g"]
    assert r["memo"][-1]["round"] == r["completed"]["summary"]["rounds"]


def test_exercise_runs_real_scripts():
    r = simulate_dispatch(
        "scd.assaylib.testing.exercise",
        {"n": 3, "cmd": 'echo "!!!screendoor:payload $((i*i))"'},
    )
    outcomes = r["completed"]["summary"]["outcomes"]
    assert [o["result"] for o in outcomes] == [0, 1, 4]


def test_exercise_pure_failure():
    d = {"assay_kwargs": {"n": 2}}
    trials = [trial({"i": 0}), trial({"i": 1}, "failed")]
    assert kinds(ex_churn(d, *records(*trials), [])) == ["fail"]


def test_jenga_takes_bare_true():
    r = simulate_dispatch(
        "scd.assaylib.skeletonization.jenga",
        {"components": list("abc"), "cmd": "x"},
        fake_trial=lambda t: "b" in t["env"]["components"].split(),
    )
    assert r["completed"]["summary"]["retained"] == ["b"]
