import random

import pytest

from screendoor import act
from screendoor.rng import derive_seed, step_seed, trial_seed


def test_launch_validates():
    a = act.launch([{"key": {"i": 1}, "cmd": "echo", "env": {"i": "1"}}])
    assert a["action"] == "launch"
    assert (
        act.launch([{"key": 1, "cmd": "x"}])["kwargs"]["trials"][0]["env"]
        == {}
    )
    with pytest.raises(TypeError, match="string"):
        act.launch([{"key": 1, "cmd": "x", "env": {"i": 1}}])
    with pytest.raises(ValueError, match="reserved"):
        act.launch([{"key": 1, "cmd": "x", "env": {"SCREENDOOR_SEED": "1"}}])
    with pytest.raises(ValueError, match="JSON"):
        act.launch([{"key": {1, 2}, "cmd": "x"}])
    with pytest.raises(ValueError, match="unknown"):
        act.launch([{"key": 1, "cmd": "x", "bogus": 1}])


def test_constructors():
    assert act.progress(1, 4)["kwargs"] == {"done": 1, "total": 4}
    assert act.succeed({"a": 1})["kwargs"]["summary"] == {"a": 1}
    assert act.fail("why")["kwargs"]["reason"] == "why"
    assert act.warning("w", dedupe_key="k")["kwargs"]["dedupe_key"] == "k"
    act.eta("2026-11-11T10:00:00+00:00")
    with pytest.raises(ValueError):
        act.eta("not a time")
    with pytest.raises(TypeError):
        act.memo([1])


def test_seeds():
    assert derive_seed(1, "a") == derive_seed(1, "a")
    assert derive_seed(1, "a") != derive_seed(1, "b")
    assert 0 <= derive_seed(1) < 2**32
    assert step_seed(5, 1, 2) != step_seed(5, 2, 2)
    assert trial_seed(5, "u") == derive_seed(5, "trial", "u")
    random.Random(step_seed(5, 0, 0))  # usable as a seed
