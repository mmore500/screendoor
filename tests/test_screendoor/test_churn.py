import random
import sys

import pytest

from screendoor import churn as scd_churn
from screendoor.testing import simulate_dispatch


def test_launch_validates():
    a = scd_churn.launch([{"key": {"i": 1}, "cmd": "echo", "env": {"i": "1"}}])
    assert a["action"] == "launch"
    assert (
        scd_churn.launch([{"key": 1, "cmd": "x"}])["kwargs"]["trials"][0][
            "env"
        ]
        == {}
    )
    with pytest.raises(TypeError, match="string"):
        scd_churn.launch([{"key": 1, "cmd": "x", "env": {"i": 1}}])
    with pytest.raises(ValueError, match="reserved"):
        scd_churn.launch(
            [{"key": 1, "cmd": "x", "env": {"SCREENDOOR_SEED": "1"}}]
        )
    with pytest.raises(ValueError, match="JSON"):
        scd_churn.launch([{"key": {1, 2}, "cmd": "x"}])
    with pytest.raises(ValueError, match="unknown"):
        scd_churn.launch([{"key": 1, "cmd": "x", "bogus": 1}])


def test_constructors():
    assert scd_churn.progress(1, 4)["kwargs"] == {"done": 1, "total": 4}
    assert scd_churn.succeed({"a": 1})["kwargs"]["summary"] == {"a": 1}
    assert scd_churn.fail("why")["kwargs"]["reason"] == "why"
    assert (
        scd_churn.warning("w", dedupe_key="k")["kwargs"]["dedupe_key"] == "k"
    )
    scd_churn.eta("2026-11-11T10:00:00+00:00")
    with pytest.raises(ValueError):
        scd_churn.eta("not a time")
    with pytest.raises(TypeError):
        scd_churn.memo([1])


def _draw(dispatch, trial_submissions, trial_payloads, memo):
    draws = [random.random()]
    if "numpy" in sys.modules:
        draws.append(float(sys.modules["numpy"].random.random()))
    return draws


def test_seed_global_rngs_is_a_function_of_dispatch_state():
    seeded = scd_churn.seed_global_rngs(_draw)
    d = {"meta_seed": 7}
    first = seeded(d, [{}] * 3, [], [1])
    random.seed()  # scramble between calls
    assert seeded(d, [{}] * 3, [], [1]) == first
    assert seeded(d, [{}] * 4, [], [1]) != first  # another trial submission
    assert seeded(d, [{}] * 3, [], [1, 2]) != first  # another memo
    assert seeded({"meta_seed": 8}, [{}] * 3, [], [1]) != first
    seed = scd_churn.churn_seed(7, 1, 3)
    assert 0 <= seed < 2**32
    assert first[0] == random.Random(seed).random()


def test_seed_global_rngs_seeds_numpy():
    numpy = pytest.importorskip("numpy")
    seeded = scd_churn.seed_global_rngs(_draw)
    _, a = seeded({"meta_seed": 1}, [], [], [])
    numpy.random.seed(12345)
    _, b = seeded({"meta_seed": 1}, [], [], [])
    assert a == b


def test_seed_global_rngs_takes_an_assay_module():
    from screendoor.assaylib.testing import exercise

    seeded = scd_churn.seed_global_rngs(exercise)
    assert seeded.__wrapped__ is exercise.churn
    r = simulate_dispatch(
        "scd.churn.seed_global_rngs(scd.assaylib.testing.exercise)",
        {"n": 2},
        fake_trial=lambda t: True,
    )
    assert r["completed"]["outcome"] == "succeeded"


def test_library_leaves_global_rngs_alone():
    random.seed(99)
    state = random.getstate()
    simulate_dispatch(
        "scd.assaylib.testing.exercise",
        {"n": 3},
        fake_trial=lambda t: True,
    )
    assert random.getstate() == state


def test_fold_trials_merges_raw_records():
    ts = "2026-11-11T00:00:00+00:00"
    base = {"trial_uuid": "u", "ts": ts}
    subs = [
        {**base, "event": "requested", "attempt": 0, "key": 1, "request": {}},
        {**base, "event": "requested", "attempt": 1, "key": 1, "request": {}},
    ]
    pays = [{**base, "event": "completed", "attempt": 1, "result": 9}]
    (t,) = scd_churn.fold_trials(subs, [])
    assert (t["status"], t["state"], t["attempt"]) == (
        "requested",
        "pending",
        1,
    )
    (t,) = scd_churn.fold_trials(subs, pays)
    assert (t["status"], t["state"], t["result"]) == (
        "succeeded",
        "complete",
        9,
    )
    assert t["retries"] == 1
    assert scd_churn.fold_trials([], pays) == []  # no submission: no trial
