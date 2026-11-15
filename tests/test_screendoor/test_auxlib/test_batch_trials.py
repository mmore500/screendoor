from screendoor.auxlib._batch_trials import batch_trials


def trial(name, weight=None):
    request = {"cmd": "x", "env": {}}
    if weight is not None:
        request["weight"] = weight
    return {"trial_uuid": name, "request": request}


def names(batches):
    return ["".join(t["trial_uuid"] for t in b) for b in batches]


def test_unweighted_trials_batch_by_count():
    assert names(batch_trials([trial(c) for c in "abcde"], 2)) == [
        "ab",
        "cd",
        "e",
    ]
    assert batch_trials([], 3) == []


def test_weights_fill_a_batch():
    trials = [trial("a", 3), trial("b"), trial("c", 2), trial("d", 2)]
    assert names(batch_trials(trials, 4)) == ["ab", "cd"]
    assert names(batch_trials(trials, 5)) == ["ab", "cd"]
    assert names(batch_trials(trials, 6)) == ["abc", "d"]


def test_a_trial_heavier_than_a_batch_runs_alone():
    trials = [trial("a"), trial("b", 9), trial("c"), trial("d")]
    assert names(batch_trials(trials, 2)) == ["a", "b", "cd"]


def test_fractional_weights():
    trials = [trial(c, 0.5) for c in "abcde"]
    assert names(batch_trials(trials, 2)) == ["abcd", "e"]
