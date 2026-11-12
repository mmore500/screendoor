import random

from screendoor.assaylib.knockout.naive_exhaustive import churn as ko_churn
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


def test_naive_exhaustive_pure():
    d = {"assay_kwargs": {"targets": ["a", "b"], "threshold": 0.1, "cmd": "x"}}
    launch, progress = ko_churn(d, [], [], [])
    assert kinds([launch, progress]) == ["launch", "progress"]
    assert len(launch["kwargs"]["trials"]) == 3
    trials = [
        trial({"knockout": None}, result={"score": 1.0}),
        trial({"knockout": "a"}, result={"score": 0.5}),
        trial({"knockout": "b"}, "running"),
    ]
    assert kinds(ko_churn(d, *records(*trials), [])) == ["progress"]
    trials[2] = trial({"knockout": "b"}, result={"score": 0.95})
    (a,) = ko_churn(d, *records(*trials), [])
    assert a["action"] == "succeed"
    assert a["kwargs"]["summary"]["hits"] == ["a"]


def test_naive_exhaustive_baseline_fail():
    d = {"assay_kwargs": {"targets": ["a"], "threshold": 0.1, "cmd": "x"}}
    trials = [
        trial({"knockout": None}, "failed"),
        trial({"knockout": "a"}, result={"score": 1}),
    ]
    assert kinds(ko_churn(d, *records(*trials), [])) == ["fail"]


def test_null_results_count_as_failed():
    d = {"assay_kwargs": {"targets": ["a"], "threshold": 0.1, "cmd": "x"}}
    trials = [
        trial({"knockout": None}, result={"score": 1.0}),
        trial({"knockout": "a"}),  # succeeded, but sent no result
    ]
    assert kinds(ko_churn(d, *records(*trials), [])) == ["fail"]
    d["assay_kwargs"]["max_failed"] = 1
    (a,) = ko_churn(d, *records(*trials), [])
    assert a["kwargs"]["summary"] == {
        "baseline": 1.0,
        "hits": [],
        "failed": ["a"],
    }


def test_jenga_simulated():
    r = simulate_dispatch(
        "scd.assaylib.skeletonize.naive_jenga",
        {"components": list("abcdefgh"), "cmd": "x", "width": 3},
        fake_trial=lambda t: {
            "passes": {"b", "g"} <= set(t["env"]["components"].split())
        },
    )
    assert r["closed"]["outcome"] == "succeeded"
    assert r["closed"]["summary"]["skeleton"] == ["b", "g"]
    assert r["memo"][-1]["round"] == r["closed"]["summary"]["rounds"]


def test_exercise_runs_real_scripts():
    r = simulate_dispatch(
        "scd.assaylib.testing.exercise",
        {"n": 3, "cmd": 'echo "!!!screendoor:result $((i*i))"'},
    )
    outcomes = r["closed"]["summary"]["outcomes"]
    assert [o["result"] for o in outcomes] == [0, 1, 4]


def test_exercise_pure_failure():
    d = {"assay_kwargs": {"n": 2}}
    trials = [trial({"i": 0}), trial({"i": 1}, "failed")]
    assert kinds(ex_churn(d, *records(*trials), [])) == ["fail"]
