import json
import math
import random

import pytest

from screendoor.assaylib import skeletonization
from screendoor.assaylib.skeletonization.staged._StagedSearch import (
    StagedSearch,
)
from screendoor.assaylib.skeletonization.staged._fit_effects import fit_effects
from screendoor.auxlib import decode_sites
from screendoor.auxlib._DispatchContext import load_dispatches
from screendoor.testing import simulate_dispatch


class Toy:
    """A toy genome: critical sites and redundant sets (harmless until
    every member is out) fail every screen, and each other site costs a
    little; a screen also fails a knockout whose summed costs reach what it
    detects."""

    def __init__(self, n, critical=(), sets=(), costs=None, detects=()):
        self.n = n
        self.critical = frozenset(critical)
        self.sets = [frozenset(s) for s in sets]
        self.costs = costs or {}
        self.detects = detects  # the loss each screen detects

    def large(self, deleted):
        return bool(deleted & self.critical) or any(
            s <= deleted for s in self.sets
        )

    def loss(self, deleted):
        return sum(c for i, c in self.costs.items() if i in deleted)

    def fails(self, deleted, tier):
        detects = self.detects[tier] if self.detects else math.inf
        return self.large(deleted) or self.loss(deleted) >= detects - 1e-12


def drive(toy, sd=0.02, **kw):
    """Run a StagedSearch against a toy without a daemon. Returns the
    search, its result, and every request it made."""
    kw = {"abs_tol": 0.06, **kw}
    search = StagedSearch(toy.n, kw, seed=1, num_control_trials=40)
    run, answers, asked = search.run(), None, []
    while True:
        try:
            wave = run.send(answers)
        except StopIteration as stop:
            return search, stop.value, asked
        asked += wave
        answers = []
        for kind, stage, deleted, *index in wave:
            if kind == "screen":
                answers.append(toy.fails(deleted, stage))
            else:
                rng = random.Random(f"{stage}:{sorted(deleted)}:{index}")
                lost = toy.loss(deleted) + 0.5 * toy.large(deleted)
                answers.append(-lost + rng.gauss(0.0, sd))


# -- the regression ---------------------------------------------------------


def test_fit_effects_recovers_costs_and_their_error():
    rng = random.Random(0)
    sites = list(range(5, 25))
    truth = {i: 0.01 * (i % 4) for i in sites}
    knockouts = [
        frozenset(i for i in sites if rng.random() < 0.4) for _ in range(300)
    ]
    exact = [sum(truth[i] for i in k) for k in knockouts]
    effects, error = fit_effects(knockouts, exact, sites)
    assert effects == pytest.approx(truth, abs=1e-9) and error < 1e-9
    # with noise, the estimates are off by about the standard error
    noisy = [x + rng.gauss(0.0, 0.02) for x in exact]
    effects, error = fit_effects(knockouts, noisy, sites)
    want = 0.02 / math.sqrt(300 * 0.4 * 0.6)
    assert error == pytest.approx(want, rel=0.25)
    off = [effects[i] - truth[i] for i in sites]
    assert math.sqrt(sum(x * x for x in off) / 20) == pytest.approx(
        want, rel=0.5
    )
    # fewer trials than sites cannot be told apart
    assert fit_effects(knockouts[:10], noisy[:10], sites)[1] == math.inf


# -- the screens ------------------------------------------------------------


def test_screens_find_critical_sites_and_redundant_sets():
    toy = Toy(60, critical={3, 17, 40}, sets=[{5, 22}, {9, 11}, {30, 31, 50}])
    search, result, asked = drive(toy)
    assert result["critical"] == [3, 17, 40]
    assert sorted(s for _, s in result["redundant"]) == [
        [5, 22],
        [9, 11],
        [30, 31, 50],
    ]
    assert result["kept"] == [5, 9, 30] and result["certified"]
    # every site but the critical and kept ones is deleted
    assert result["retained"] == {3, 17, 40, 5, 9, 30}
    screens = [r for r in asked if r[0] == "screen"]
    assert len(screens) == search.stats["screen_trials"][0]
    assert len(screens) < 250  # of 1,770 pairs alone
    # the whole pool, knocked out together, was screened and passed
    pool = frozenset(range(60)) - {3, 17, 40, 5, 9, 30}
    assert ("screen", 0, pool) in screens and not toy.fails(pool, 0)


def test_screens_answer_what_earlier_trials_imply():
    search = StagedSearch(10, {}, seed=0, num_control_trials=2)
    run = search.screen([frozenset({1, 2, 3}), frozenset({4})], 0)
    assert next(run) == [
        ("screen", 0, frozenset({1, 2, 3})),
        ("screen", 0, frozenset({4})),
    ]
    with pytest.raises(StopIteration) as stop:
        run.send([False, True])
    assert stop.value.value == [False, True]
    assert search.known(frozenset({1, 3}), 0) is False  # inside a pass
    assert search.known(frozenset({4, 9}), 0) is True  # holds a lethal set
    assert search.known(frozenset({1, 9}), 0) is None
    assert search.known(frozenset(), 0) is False  # the wildtype
    # nothing new is asked for, and a repeat within a wave is asked once
    run = search.screen([frozenset({2}), frozenset({7}), frozenset({7})], 0)
    assert next(run) == [("screen", 0, frozenset({7}))]


def test_shrink_gives_up_past_max_set_size():
    search = StagedSearch(
        12, {"max_set_size": 2}, seed=0, num_control_trials=2
    )

    def shrunk(lethal):
        run, answer = search.shrink(frozenset(range(12)), 0), None
        while True:
            try:
                [(kind, tier, deleted)] = run.send(answer)
            except StopIteration as stop:
                return stop.value
            assert (kind, tier) == ("screen", 0)
            answer = [lethal <= deleted]

    assert shrunk(frozenset({7})) == {7}
    assert shrunk(frozenset({2, 9})) == {2, 9}
    assert shrunk(frozenset({2, 5, 9})) is None


def test_one_screen_leaves_small_losses_adding_up_to_the_ranking():
    """Eight sites cost 0.02 each and the screen detects 0.10: any five
    fail it together. The jackknife finds that those losses add up, and
    that no site of them fails alone, so none is kept."""
    costs = dict.fromkeys(range(10, 18), 0.02)
    toy = Toy(40, critical={3}, sets=[{5, 22}], costs=costs, detects=(0.10,))
    search, result, _ = drive(toy)
    assert result["critical"] == [3] and result["kept"] == [5]
    assert result["redundant"] == [(0, [5, 22])]
    assert result["adding_up"] and not result["certified"]
    assert all(
        tier == 0 and len(s) == 5 and set(s) <= set(costs)
        for tier, s in result["adding_up"]
    )
    # each jackknifed knockout is scored once, however many sets hold it
    assert search.stats["jackknife_trials"] == 4 * len(search.scored)
    # the ranking and confirmation then delete what fits the margin
    deleted = frozenset(range(40)) - result["retained"]
    assert toy.loss(deleted) <= 0.06 and len(deleted) >= 30


def test_second_screen_finds_sites_harmful_alone():
    """Six sites cost 0.045 each: over the 0.06 margin in pairs and
    detected alone only by the second screen. Twelve cost 0.004."""
    costs = {**dict.fromkeys(range(10, 16), 0.045)}
    costs.update(dict.fromkeys(range(20, 32), 0.004))
    toy = Toy(
        60,
        critical={3, 40},
        sets=[{5, 44}, {9, 50}],
        costs=costs,
        detects=(0.10, 0.04),
    )
    search, result, _ = drive(toy, screens=2)
    assert result["critical"] == [3, *range(10, 16), 40]
    assert result["kept"] == [5, 9]  # no harmless site is kept
    assert result["certified"]
    assert search.stats["screen_trials"][1] > 0
    deleted = frozenset(range(60)) - result["retained"]
    assert toy.loss(deleted) <= 0.06 and not toy.large(deleted)
    assert len(deleted) >= 36 + 2 + 6  # the neutral sites, and some weak


@pytest.mark.parametrize("screens", [1, 2])
def test_jackknife_tells_a_redundant_set_from_losses_adding_up(screens):
    """Sites 1, 2 and 3 are redundant: harmless unless all are out. Sites
    11, 12 and 13 cost 0.05 each, which adds up to what the first screen
    detects. Both are minimal failing sets of three. Putting a member of
    the first back leaves no loss, so one of it is kept; putting a member
    of the second back leaves 0.10, and each of it fails alone. The test
    is the second screen, or long trials if there is none."""
    toy = Toy(
        30,
        sets=[{1, 2, 3}],
        costs=dict.fromkeys((11, 12, 13), 0.05),
        detects=(0.15, 0.04)[:screens],
    )
    search, result, asked = drive(toy, screens=screens)
    assert result["critical"] == [11, 12, 13]
    assert result["kept"] == [1] and result["released"] == []
    assert result["redundant"] == [(0, [1, 2, 3])]
    assert result["adding_up"] == [(0, [11, 12, 13])]
    assert result["retained"] == {1, 11, 12, 13} and result["certified"]
    jackknifed = {r[2] for r in asked if r[:2] == ("score", "jackknife")}
    if screens == 2:
        assert not jackknifed and search.stats["jackknife_trials"] == 0
    else:  # two leave-one-out knockouts settle a set whose losses add up
        assert {frozenset({2, 3}), frozenset({1, 3}), frozenset({1, 2})} <= (
            jackknifed
        )
        assert frozenset({11, 12}) not in jackknifed
        assert search.stats["jackknife_trials"] == 4 * len(jackknifed)


def test_jackknife_of_a_pair_tests_each_site_alone():
    """Of two pairs that fail the screen, one is redundant and the other
    is two sites costing 0.06 each: sites that cannot be taken out alone
    are costly, and sites that can are redundant."""
    costs = {11: 0.06, 12: 0.06, 20: 0.01}
    toy = Toy(30, critical={4}, sets=[{1, 2}], costs=costs, detects=(0.10,))
    search, result, asked = drive(toy)
    assert result["critical"] == [4, 11, 12] and result["kept"] == [1]
    assert result["redundant"] == [(0, [1, 2])]
    assert result["adding_up"] == [(0, [11, 12])]
    jackknifed = {r[2] for r in asked if r[:2] == ("score", "jackknife")}
    assert jackknifed == {frozenset({i}) for i in (1, 2, 11, 12)}
    deleted = frozenset(range(30)) - result["retained"]
    assert deleted == frozenset(range(30)) - {1, 4, 11, 12}


def test_release_frees_a_member_whose_set_is_held_elsewhere():
    search = StagedSearch(10, {}, seed=0, num_control_trials=2)
    for redundant in ({1, 2}, {2, 3}, {5, 6}):
        search.redundant.append((0, frozenset(redundant)))
        search.kept.add(min(redundant))
    assert search.kept == {1, 2, 5}
    search.critical.add(6)  # found critical later
    assert search.release() and search.kept == {2}
    assert search.released == [1, 5] and not search.release()


# -- the ranking and the confirmation ---------------------------------------


def test_ranking_stops_at_once_when_everything_fits():
    toy = Toy(40, critical={3}, costs={7: 0.01, 8: 0.01})
    search, result, _ = drive(toy)
    assert search.stats["ranking_trials"] == 200  # four trials a site
    assert result["retained"] == {3}
    assert [c["accepted"] for c in result["confirmations"]] == [True]


def test_ranking_puts_costly_sites_last_and_keeps_within_the_margin():
    costs = dict.fromkeys(range(20, 30), 0.012)
    toy = Toy(50, critical={3, 40}, sets=[{5, 44}], costs=costs)
    search, result, _ = drive(toy)
    assert set(result["ranking"][-8:]) <= set(costs)
    assert result["effects"] == sorted(result["effects"])
    deleted = frozenset(range(50)) - result["retained"]
    assert toy.loss(deleted) <= 0.06 and not toy.large(deleted)
    assert len(deleted) >= 37 + 1 + 2  # the harmless sites and some weak
    assert result["confirmations"][-1]["replicates"] <= 64
    assert search.stats["ranking_trials"] <= 3200


def test_ranking_skips_samples_that_are_not_viable():
    """A redundant set of four is past this `max_set_size`, so the screens
    leave it in the pool; samples that complete it are skipped."""
    toy = Toy(24, sets=[{1, 2, 3, 4}])
    kw = {"abs_tol": 0.06, "max_set_size": 3}
    search = StagedSearch(24, kw, seed=1, num_control_trials=40)
    run, answers = search.run(), None
    while True:
        try:
            wave = run.send(answers)
        except StopIteration as stop:
            result = stop.value
            break
        answers = []
        for kind, stage, deleted, *index in wave:
            if kind == "screen":
                answers.append(toy.fails(deleted, stage))
            elif toy.large(deleted):
                answers.append(None)
            else:
                rng = random.Random(f"{stage}:{sorted(deleted)}:{index}")
                answers.append(rng.gauss(0.0, 0.02))
    assert not result["certified"] and search.stats["nonviable"] > 0
    assert result["retained"] & {1, 2, 3, 4}  # never all four deleted


def test_reconfirm_judges_an_accepted_knockout_by_costlier_trials():
    """The costlier trial sees three times each weak site's loss, so it
    accepts fewer deleted than the confirmation alone does."""
    costs = dict.fromkeys(range(20, 30), 0.012)
    toy = Toy(50, critical={3}, costs=costs)

    def run(toy=toy, **kw):
        kw = {"abs_tol": 0.06, **kw}
        search = StagedSearch(toy.n, kw, seed=1, num_control_trials=40)
        gen, answers, asked = search.run(), None, []
        while True:
            try:
                wave = gen.send(answers)
            except StopIteration as stop:
                return search, stop.value, asked
            asked += wave
            answers = []
            for kind, stage, deleted, *index in wave:
                if kind == "screen":
                    answers.append(toy.fails(deleted, stage))
                    continue
                rng = random.Random(f"{stage}:{sorted(deleted)}:{index}")
                scale = 3.0 if stage in ("reconfirm", "recontrol") else 1.0
                answers.append(
                    -scale * toy.loss(deleted) + rng.gauss(0.0, 0.02)
                )

    _, alone, asked = run()
    assert not any(r[1] in ("recontrol", "reconfirm") for r in asked)
    assert all("reconfirm_replicates" not in c for c in alone["confirmations"])
    search, both, asked = run(reconfirm={"num_control_trials": 30})
    recontrols = [r for r in asked if r[1] == "recontrol"]
    assert sorted(r[3] for r in recontrols) == list(range(30))
    assert all(r[2] == frozenset() for r in recontrols)
    assert search.recontrols.n == 30 and search.controls.n == 40
    deleted = frozenset(range(50)) - both["retained"]
    assert len(deleted) < 50 - len(alone["retained"])
    assert 3.0 * toy.loss(deleted) <= 0.06
    # a knockout the first confirmation rejects is not reconfirmed
    again = [c for c in both["confirmations"] if "reconfirm_replicates" in c]
    assert again and any(not c["accepted"] for c in again)
    reconfirmed = {r[2] for r in asked if r[1] == "reconfirm"}
    assert len(reconfirmed) == len(again)
    with pytest.raises(ValueError, match="num_control_trials"):
        run(reconfirm={})
    # with `every` 0, the costlier trials judge only the prefix the
    # first confirmation settles on, and it searches again below what
    # they reject
    search, late, asked = run(reconfirm={"num_control_trials": 30, "every": 0})
    assert late["retained"] == both["retained"]
    rounds = late["confirmations"]
    first = next(i for i, c in enumerate(rounds) if "replicates" not in c)
    assert rounds[first]["deleted"] == 50 - len(alone["retained"])
    assert not rounds[first]["accepted"]
    below = [c["deleted"] for c in rounds[first + 1 :]]
    assert below and max(below) < rounds[first]["deleted"]
    assert search.reconfirm_every == 0
    # adaptive, a costlier test that fails halves the wait, and one that
    # passes doubles it
    again = {"num_control_trials": 30, "every": 4, "adaptive": True}
    search, paced, asked = run(reconfirm=again)
    assert paced["retained"] == both["retained"]
    costlier = [
        c for c in paced["confirmations"] if "reconfirm_replicates" in c
    ]
    verdicts = [c["accepted"] for c in costlier]
    assert True in verdicts and False in verdicts
    # what is deleted is the longest knockout the costlier test accepted
    assert 50 - len(paced["retained"]) == max(
        c["deleted"] for c in costlier if c["accepted"]
    )
    every = 4
    for accepted in verdicts:
        every = every * 2 if accepted else max(1, every // 2)
    assert search.reconfirm_every == paced["reconfirm_every"] == every
    # where the two agree, a search of few acceptances takes one costlier
    # test, however it waits
    harmless = Toy(40, critical={3})
    for every in (0, 1, 8):
        again = {"num_control_trials": 30, "every": every}
        _, same, asked = run(harmless, reconfirm=again)
        assert same["retained"] == {3}
        assert len({r[2] for r in asked if r[1] == "reconfirm"}) == 1
    with pytest.raises(ValueError, match="every"):
        run(reconfirm={"num_control_trials": 30, "every": -1})


@pytest.mark.parametrize(
    "kw",
    [
        {"screens": 0},
        {"screens": []},
        {"batch_size": 0},
        {"max_set_size": 0},
        {"jackknife_replicates": 0},
    ],
)
def test_staged_search_refuses_bad_kwargs(kw):
    with pytest.raises(ValueError):
        StagedSearch(10, kw, seed=0, num_control_trials=2)


# -- as a dispatch ----------------------------------------------------------

CRITICAL, PAIRS = {3, 17}, [{5, 22}, {9, 11}]
WEAK = dict.fromkeys((1, 7, 13, 19, 25, 28), 0.012)
KW = {"n_sites": 30, "cmd": "x", "abs_tol": 0.06, "search_seed": 1}


def fake_trial(t):
    out = frozenset(range(30)) - decode_sites(t["env"]["retained"])
    large = bool(out & CRITICAL) or any(p <= out for p in PAIRS)
    if "screen" in t["env"]:
        return not large  # a screen passes unless the failure is large
    rng = random.Random(json.dumps(t["key"], sort_keys=True))
    lost = 0.5 * large + sum(c for i, c in WEAK.items() if i in out)
    return {"score": -lost + rng.gauss(0.0, 0.02), "viable": not large}


def test_staged_dispatch():
    r = simulate_dispatch(
        "scd.assaylib.skeletonization.staged", KW, fake_trial=fake_trial
    )
    assert r["completed"]["outcome"] == "succeeded", r["completed"]
    s = r["completed"]["summary"]
    assert s["policy"] == "staged" and s["status"] == "complete"
    assert s["critical"] == "3,17" and s["kept"] == "5,9"
    assert s["redundant_sets"] == [
        {"screen": 0, "sites": "5,22"},
        {"screen": 0, "sites": "9,11"},
    ]
    assert s["pool_certified"] and s["released"] == ""
    kept = decode_sites(s["retained"])
    assert {3, 17, 5, 9} <= kept and s["retained_count"] == len(kept)
    deleted = frozenset(range(30)) - kept
    assert sum(c for i, c in WEAK.items() if i in deleted) <= 0.06
    assert len(deleted) >= 20  # every harmless site
    assert len(s["ranking"]) == len(s["effects"]) == 26
    assert s["confirmations"][0]["deleted"] == s["predicted_cutoff"]
    control = s["control"]
    assert control["n"] == 40 and control["margin"] == 0.06
    assert control["stage"]["rule"] == "sprt"
    # the trials: screens, the controls, the ranking's samples, and the
    # confirmation's fresh replicates
    keys = [t["key"] for t in r["trials"]]
    assert s["trials"] == len(keys)
    screens = [k for k in keys if "screen" in k]
    assert len(screens) == s["stats"]["screen_trials"][0]
    controls = [k for k in keys if set(k) == {"retained", "replicate"}]
    assert all(k["retained"] == "0-29" for k in controls)
    assert sorted(k["replicate"] for k in controls) == list(range(40))
    # each pair's two single knockouts, four long trials each
    jackknifed = [k for k in keys if "jackknife" in k]
    assert len(jackknifed) == s["stats"]["jackknife_trials"] == 16
    assert s["adding_up"] == []
    samples = [k["sample"] for k in keys if "sample" in k]
    assert sorted(samples) == list(range(s["stats"]["ranking_trials"]))
    confirmed = {k["retained"] for k in keys if "confirm" in k}
    assert len(confirmed) == len(s["confirmations"])


def test_staged_churn_is_pure_and_replayable():
    r = simulate_dispatch(
        "scd.assaylib.skeletonization.staged", KW, fake_trial=fake_trial
    )
    d = {"assay_kwargs": KW, "meta_seed": 9}
    churn = skeletonization.staged.churn
    (ctx,) = load_dispatches(r["dispatchdir"])
    subs, pays = ctx.read_trial_submissions(), ctx.read_trial_payloads()
    a1 = churn(d, subs, pays, [])
    a2 = churn(d, subs[::-1], pays[::-1], [])
    assert (
        a1
        == a2
        == [
            {
                "action": "succeed",
                "kwargs": {"summary": r["completed"]["summary"]},
            }
        ]
    )
    # the first wave is the controls alone
    launch, progress = churn(d, [], [], [])
    assert [t["key"] for t in launch["kwargs"]["trials"]] == [
        {"retained": "0-29", "replicate": i} for i in range(40)
    ]
    assert "controls" in progress["kwargs"]["message"]
    # cut off midway, it asks only for trials that were in fact launched
    keys = {json.dumps(t["key"], sort_keys=True) for t in r["trials"]}
    done = {p["trial_uuid"] for p in pays[: len(pays) // 3]}
    launch = churn(d, [x for x in subs if x["trial_uuid"] in done], pays, [])
    asked = launch[0]["kwargs"]["trials"]
    assert launch[0]["action"] == "launch" and asked
    assert all(json.dumps(t["key"], sort_keys=True) in keys for t in asked)


def test_staged_dispatch_of_a_pool_of_one_site():
    def fake(t):
        out = frozenset(range(2)) - decode_sites(t["env"]["retained"])
        if "screen" in t["env"]:
            return 0 not in out
        rng = random.Random(json.dumps(t["key"], sort_keys=True))
        return rng.gauss(0.0, 0.02)

    r = simulate_dispatch(
        "scd.assaylib.skeletonization.staged",
        {**KW, "n_sites": 2},
        fake_trial=fake,
    )
    assert r["completed"]["outcome"] == "succeeded", r["completed"]
    s = r["completed"]["summary"]
    assert s["critical"] == "0" and s["retained"] == "0"
    assert s["effects_error"] is None and s["stats"]["ranking_trials"] == 0


def test_staged_screens_take_their_own_cmd_and_env():
    seen = set()

    def fake(t):
        seen.add((t["cmd"], t["env"].get("screen"), t["env"].get("mode")))
        if "screen" in t["env"]:
            return {"accept": 2 in decode_sites(t["env"]["retained"])}
        assert t["env"]["wildtype"] == "abcdefgh"
        return float(len(decode_sites(t["env"]["retained"])) >= 1)

    r = simulate_dispatch(
        "scd.assaylib.skeletonization.staged.make_churn(num_control_trials=2)",
        {
            "sequence": "abcdefgh",
            "cmd": "long",
            "env": {"mode": "full"},
            "screens": [{"cmd": "short", "env": {"mode": "quick"}}, {}],
        },
        fake_trial=fake,
    )
    s = r["completed"]["summary"]
    assert r["completed"]["outcome"] == "succeeded", r["completed"]
    assert s["critical"] == "2" and s["skeleton"] == "AAcAAAAA"
    assert s["control"]["sd"] == 0 and s["stats"]["screen_trials"][1] > 0
    assert seen == {
        ("short", "0", "quick"),
        ("long", "1", "full"),
        ("long", None, "full"),
    }


def test_staged_reconfirmation_takes_its_own_env_and_controls():
    def fake(t):
        costly = "reconfirm" in t["key"]
        assert t["env"].get("size") == ("big" if costly else None)
        assert t["env"].get("reconfirm") == ("1" if costly else None)
        return fake_trial(t)

    r = simulate_dispatch(
        "scd.assaylib.skeletonization.staged",
        {
            **KW,
            "reconfirm": {
                "num_control_trials": 20,
                "env": {"size": "big"},
                "cmd": "y",
            },
        },
        fake_trial=fake,
    )
    assert r["completed"]["outcome"] == "succeeded", r["completed"]
    s = r["completed"]["summary"]
    assert s["reconfirm_control"]["n"] == 20 and s["control"]["n"] == 40
    assert s["confirmations"][-1]["reconfirm_replicates"] > 0
    again = [t for t in r["trials"] if "reconfirm" in t["key"]]
    assert all(t["request"]["cmd"] == "y" for t in again)
    controls = [t["key"] for t in again if t["key"]["retained"] == "0-29"]
    assert sorted(k["replicate"] for k in controls) == list(range(20))
    assert len(again) > 20
    plain = [t for t in r["trials"] if "reconfirm" not in t["key"]]
    assert all(t["request"]["cmd"] == "x" for t in plain)


@pytest.mark.parametrize(
    "kw,fake,reason",
    [
        ({}, lambda t: {"accept": True}, "needs scores"),
        ({"screens": 0}, fake_trial, "must be positive"),
        ({"abs_tol": 0.0}, fake_trial, "needs a margin"),
        ({"control_test": "rank"}, fake_trial, "control_test"),
    ],
)
def test_staged_dispatch_refuses_bad_settings(kw, fake, reason):
    r = simulate_dispatch(
        "scd.assaylib.skeletonization.staged",
        {**KW, **kw},
        fake_trial=fake,
        churn_maxretry=0,
    )
    assert r["completed"]["outcome"] == "failed"
    assert reason in r["completed"]["reason"]
