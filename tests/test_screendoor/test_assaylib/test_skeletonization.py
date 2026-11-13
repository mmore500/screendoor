import asyncio
import inspect
import itertools
import json
import math
import os
import random
import sys

import pytest

from screendoor.assaylib import skeletonization
from screendoor.assaylib.skeletonization.gama._churn import GamaSearch
from screendoor.auxlib import decode_sites, encode_sites
from screendoor.auxlib._DispatchContext import load_dispatches
from screendoor.testing import simulate_dispatch

OLD = os.path.expanduser("~/2026-11-03")
PORTED = ["ddmin", "minesweeper", "hybrid"]  # from 2026-11-03
POLICIES = [*PORTED, "gama"]
# the paper's population sizes are for a cluster: the tests use small ones
GAMA_SMALL = {
    "guess_subsets": 24,
    "add_combinations": 64,
    "elite_size": 10,
    "mate_children": 48,
    "mate_patience": 4,
}


def test_codec_roundtrip():
    rng = random.Random(0)
    for _ in range(200):
        s = frozenset(rng.sample(range(60), rng.randrange(61)))
        assert decode_sites(encode_sites(s)) == s
    assert encode_sites({0, 1, 2, 5, 7, 8}) == "0-2,5,7-8"
    assert encode_sites(set()) == ""


def _pred(essential, groups=()):
    """Acceptable: keeps every essential site and one site of each group."""

    def acceptable(retained):
        return essential <= retained and all(g & retained for g in groups)

    return acceptable


def _kwargs(policy, n, **kw):
    small = GAMA_SMALL if policy == "gama" else {}
    return {"n_sites": n, "cmd": "x", **small, **kw}


def _sim(policy, n, pred, **kw):
    return simulate_dispatch(
        f"scd.assaylib.skeletonization.{policy}",
        _kwargs(policy, n, **kw),
        fake_trial=lambda t: {
            "accept": pred(decode_sites(t["env"]["retained"]))
        },
    )


@pytest.mark.parametrize("policy", POLICIES)
def test_finds_one_minimal_skeleton(policy):
    groups = [frozenset({20, 21}), frozenset({30, 35, 39})]
    pred = _pred(frozenset({0, 1, 2, 10, 44}), groups)
    r = _sim(policy, 45, pred, batch_size=6, search_seed=3)
    s = r["completed"]["summary"]
    kept = decode_sites(s["retained"])
    assert s["certified"] and pred(kept)
    assert all(not pred(kept - {i}) for i in kept)  # single-deletion minimal
    assert len(kept) == 7
    assert s["trials"] == len(r["trials"])


@pytest.mark.parametrize("policy", POLICIES)
def test_churn_is_pure_and_replayable(policy):
    pred = _pred(frozenset({3, 9}))
    r = _sim(policy, 16, pred, batch_size=4, search_seed=7)
    d = {
        "assay_kwargs": _kwargs(policy, 16, batch_size=4, search_seed=7),
        "meta_seed": 1,
        "dispatch_uuid": r["dispatch_uuid"],
    }
    churn = getattr(skeletonization, policy).churn
    (ctx,) = load_dispatches(r["dispatchdir"])
    subs, pays = ctx.read_trial_submissions(), ctx.read_trial_payloads()
    a1 = churn(d, subs, pays, [])
    a2 = churn(d, subs[::-1], pays[::-1], [])
    assert a1 == a2  # independent of record order
    assert a1[0]["action"] == "succeed"


def test_rel_tol_and_tasks_and_replicates():
    def fake(t):
        kept = decode_sites(t["env"]["retained"])
        rep = int(t["env"]["replicate"])
        score = 1.0 - 0.01 * (12 - len(kept)) + (0.001 if rep else -0.001)
        return {
            "score": score,
            "viable": 0 in kept,
            "tasks": [int(5 in kept), 1],
        }

    r = simulate_dispatch(
        "scd.assaylib.skeletonization.hybrid",
        {
            "n_sites": 12,
            "cmd": "x",
            "batch_size": 4,
            "rel_tol": 0.035,
            "require_atleast": ["tasks"],
            "replicates": 2,
        },
        fake_trial=fake,
    )
    s = r["completed"]["summary"]
    kept = decode_sites(s["retained"])
    assert {0, 5} <= kept
    assert len(kept) == 12 - 3  # 3% loss allowed, 4% is not
    candidates = [t for t in r["trials"] if t["key"]["retained"] != "0-11"]
    assert {t["key"]["replicate"] for t in candidates} == {0, 1}


def test_trial_failure_fails_dispatch():
    def fake(t):
        if "7" not in t["env"]["knockout"].replace("-", ",").split(","):
            return {"accept": True}
        raise RuntimeError("simulator crashed")

    r = simulate_dispatch(
        "scd.assaylib.skeletonization.ddmin",
        {"n_sites": 8, "cmd": "x"},
        fake_trial=fake,
        churn_maxretry=0,
    )
    assert r["completed"]["outcome"] == "failed"
    assert "(failed, key" in r["completed"]["reason"]


def test_sequence_env_and_skeleton():
    seq = "abcdefgh"
    r = simulate_dispatch(
        "scd.assaylib.skeletonization.minesweeper",
        {"sequence": seq, "cmd": "x", "batch_size": 4},
        fake_trial=lambda t: {
            "accept": "c" in t["env"]["sequence"]
            and "g" in t["env"]["sequence"]
        },
    )
    assert r["completed"]["summary"]["skeleton"] == "AAcAAAgA"


def test_first_wave_launches_with_baseline():
    d = {
        "assay_kwargs": {"n_sites": 16, "cmd": "x", "batch_size": 8},
        "meta_seed": 5,
        "dispatch_uuid": "00000000-0000-0000-0000-000000000000",
    }
    (launch, progress) = skeletonization.hybrid.churn(d, [], [], [])
    keys = [t["key"] for t in launch["kwargs"]["trials"]]
    wildtype = [k for k in keys if k["retained"] == "0-15"]
    assert wildtype == [
        {"retained": "0-15", "replicate": r} for r in range(40)
    ]
    assert len(keys) == 8 + 40  # a wave of candidates, and the controls
    assert progress["action"] == "progress"
    churn = skeletonization.hybrid.make_churn(num_control_trials=3)
    (launch, _) = churn(d, [], [], [])
    assert len(launch["kwargs"]["trials"]) == 8 + 3


@pytest.mark.parametrize("policy", POLICIES)
def test_make_churn_takes_a_defaulted_keyword(policy):
    make_churn = getattr(skeletonization, policy).make_churn
    (param,) = inspect.signature(make_churn).parameters.values()
    assert param.name == "num_control_trials" and param.default == 40
    assert param.kind is param.KEYWORD_ONLY
    with pytest.raises(ValueError):
        make_churn(num_control_trials=0)


@pytest.mark.skipif(
    not os.path.isdir(os.path.join(OLD, "knockout_skeleton")),
    reason="needs ~/2026-11-03/knockout_skeleton",
)
@pytest.mark.parametrize(
    "kind,n,b,seed,policy",
    list(
        itertools.product(
            ["essential", "redundancy", "mixed"],
            [16, 50],
            [4, 8, 12],
            [0, 1],
            PORTED,
        )
    ),
)
def test_matches_2026_11_03_implementation(kind, n, b, seed, policy):
    """Same skeleton, batch count and certificate as the original code."""
    sys.path.insert(0, OLD)
    from knockout_skeleton import ExactEvaluator, SearchConfig, skeletonize
    from knockout_skeleton.landscapes import make_landscape

    land = make_landscape(kind, n=n, seed=seed)
    ref = asyncio.run(
        skeletonize(
            range(n),
            ExactEvaluator(land, max_parallel=b),
            SearchConfig(policy=policy, batch_size=b, seed=seed),
        )
    )
    r = _sim(policy, n, land, batch_size=b, search_seed=seed)
    s = r["completed"]["summary"]
    assert decode_sites(s["retained"]) == ref.retained
    assert s["proposal_batches"] == ref.proposal_batches
    assert s["certified"] == ref.certified


def test_bare_number_results_are_scores():
    need = frozenset({2, 5})
    r = simulate_dispatch(
        "scd.assaylib.skeletonization.hybrid",
        {"n_sites": 8, "cmd": "x", "batch_size": 4, "rel_tol": 0.1},
        fake_trial=lambda t: float(need <= decode_sites(t["env"]["retained"])),
    )
    assert r["completed"]["outcome"] == "succeeded"
    assert decode_sites(r["completed"]["summary"]["retained"]) == need


def test_result_without_score_fails_the_dispatch():
    r = simulate_dispatch(
        "scd.assaylib.skeletonization.ddmin",
        {"n_sites": 4, "cmd": "x"},
        fake_trial=lambda t: {"viable": True},
        churn_maxretry=0,
    )
    assert r["completed"]["outcome"] == "failed"
    assert "lacks ['score']" in r["completed"]["reason"]


def _drive(search, pred):
    """Run a search against ``pred`` without a daemon. Returns its result
    and the genotypes it asked about, wave by wave, audits aside."""
    run, waves, verdicts = search.run(), [], None
    while True:
        try:
            wave = run.send(verdicts)
        except StopIteration as stop:
            return stop.value, waves
        if not wave["fresh"]:
            waves.append(wave["genotypes"])
        verdicts = {
            g: "accept" if pred(g) else "reject" for g in wave["genotypes"]
        }


def _gama(n, seed=0, batch_size=8, **kw):
    return GamaSearch(
        range(n), batch_size=batch_size, seed=seed, **{**GAMA_SMALL, **kw}
    )


def test_gama_guess_deletes_half_to_all_of_one_set():
    members = list(range(10, 21))
    masks = _gama(40, guess_subsets=400).guess(members)
    assert len(masks) == len(set(masks)) > 100
    assert all(d <= set(members) for d in masks)
    assert {len(d) for d in masks} == set(range(6, 12))  # 50% to 100% of 11
    (whole,) = _gama(40, guess_min_fraction=1).guess(members)
    assert whole == set(members)


def test_gama_child_mixes_two_parents():
    search = _gama(30, mutation_probability=0)
    a, b = frozenset(range(0, 12)), frozenset(range(6, 20))
    search.elite = [a, b]
    children = [search.child() for _ in range(400)]
    assert all(a & b <= c <= a | b for c in children)
    assert len(set(children)) > 100
    # a site only one parent deletes is inherited about half the time
    inherited = sum(len(c - (a & b)) for c in children) / len(children)
    assert 0.4 < inherited / len(a ^ b) < 0.6


def test_gama_child_mutates_anywhere_in_the_genome():
    search = _gama(30, mutation_probability=1)
    parent = frozenset(range(10, 20))
    search.elite = [parent]  # a lone parent mates with itself
    children = [search.child() for _ in range(400)]
    flips = [len(c ^ parent) for c in children]
    assert min(flips) >= 1
    assert 2 < sum(flips) / len(flips) < 3  # mean 2, rounded, never zero
    assert any(c - parent for c in children)  # knockouts
    assert any(parent - c for c in children)  # knock-ins
    assert set().union(*children) == set(range(30))
    search.mutation_probability = 0
    assert search.child() == parent


def test_gama_stages_build_on_each_other():
    groups = [frozenset({20, 21}), frozenset({30, 35, 39})]
    pred = _pred(frozenset({0, 1, 2, 10, 44}), groups)
    search = _gama(45, seed=3)
    result, waves = _drive(search, pred)
    stats = search.stats
    assert stats["candidates"] == 40  # 45 less the 5 essential sites
    assert len(stats["guess_viable"]) == 4
    assert stats["add_viable"] > 0 and stats["generations"] >= 4
    by_stage = stats["deleted"]
    assert by_stage["guess"] <= 10  # a guess stays within its set of 10
    assert by_stage["guess"] < by_stage["add"] <= by_stage["mate"] == 38
    # one commit, of the best deletion; then the sweep finds nothing more
    (commit,) = result["transitions"]
    assert commit[2:] == ("deletion", "gama")
    assert len(result["retained"]) == 7 and result["certified"]
    assert all(len(w) <= 8 for w in waves)
    asked = [g for w in waves for g in w]
    assert len(asked) == len(set(asked))  # no genotype is tested twice


def test_gama_mate_deletes_a_site_essential_on_its_own():
    """Only Mate's mutations reach site 3, which can go once 7 has."""

    def pred(retained):
        return {0, 1} <= retained and (3 in retained or 7 not in retained)

    search = _gama(12, seed=1)
    result, _ = _drive(search, pred)
    assert search.stats["candidates"] == 9  # not 0, 1 or 3
    assert search.stats["deleted"]["add"] <= 9
    assert search.stats["deleted"]["mate"] == 10
    assert result["retained"] == {0, 1}
    assert [t[3] for t in result["transitions"]] == ["gama"]


def test_gama_batch_size_sets_the_pace_only():
    pred = _pred(
        frozenset({3, 9, 27}), [frozenset({5, 6}), frozenset({14, 30})]
    )
    runs = []
    for b in (1, 5, 64):
        search = _gama(32, seed=2, batch_size=b)
        result, waves = _drive(search, pred)
        assert all(len(w) <= b for w in waves)
        runs.append((search.stats, result["transitions"][0]))
    assert runs[0] == runs[1] == runs[2]


@pytest.mark.parametrize(
    "kw,generations",
    [
        ({"mate_generations": 0}, None),
        ({"mate_children": 0}, None),
        ({"mate_generations": 3, "mate_patience": None}, 3),
        ({"mate_generations": 50, "mate_patience": 1}, 2),
    ],
)
def test_gama_mate_stops(kw, generations):
    pred = _pred(frozenset({0, 5}))
    search = _gama(12, **kw)
    result, _ = _drive(search, pred)
    assert search.stats.get("generations") == generations
    assert ("mate" in search.stats["deleted"]) == bool(generations)
    assert result["retained"] == {0, 5} and result["certified"]


def test_gama_degrades_to_single_knockouts():
    """With no viable guess, Mate starts from the single knockouts."""
    pred = _pred(frozenset({1}), [frozenset({4, 5}), frozenset({8, 9})])
    search = _gama(12, guess_subsets=0, mate_patience=8)
    result, _ = _drive(search, pred)
    assert search.stats["guess_viable"] == [0, 0, 0, 0]
    assert "add_viable" not in search.stats
    assert search.stats["deleted"]["guess"] == 1
    assert search.stats["deleted"]["mate"] > 1
    assert len(result["retained"]) == 3 and result["certified"]


@pytest.mark.parametrize("n,kept", [(1, 0), (1, 1), (2, 0), (3, 3), (6, 5)])
def test_gama_tiny_genomes(n, kept):
    result, _ = _drive(_gama(n), lambda retained: len(retained) >= kept)
    assert len(result["retained"]) == kept and result["certified"]


@pytest.mark.parametrize(
    "kw",
    [
        {"guess_sets": 0},
        {"elite_size": 0},
        {"mate_children": -1},
        {"mate_patience": 0},
        {"guess_min_fraction": 0},
        {"mutation_probability": 1.5},
        {"mutation_mean": 0},
    ],
)
def test_gama_rejects_bad_kwargs(kw):
    with pytest.raises(ValueError):
        _gama(8, **kw)


def test_gama_dispatch_reports_stages_and_keeps_best_when_out_of_budget():
    pred = _pred(frozenset({0, 1, 2, 10, 44}))
    r = _sim("gama", 45, pred, batch_size=16, search_seed=3)
    s = r["completed"]["summary"]
    assert s["policy"] == "gama" and s["certified"]
    assert s["stats"]["deleted"]["mate"] == 40 == 45 - s["retained_count"]
    # stopped during Add: the best guess so far, acceptable but uncertified
    r = _sim(
        "gama", 45, pred, batch_size=16, search_seed=3, max_proposal_batches=9
    )
    s = r["completed"]["summary"]
    assert r["completed"]["outcome"] == "succeeded"
    assert not s["certified"] and s["status"] == "unresolved"
    assert s["proposal_batches"] == 9
    assert set(s["stats"]["deleted"]) == {"guess"}
    assert 45 - s["retained_count"] == s["stats"]["deleted"]["guess"] > 1
    assert pred(decode_sites(s["retained"]))


# -- judging scores against wildtype-vs-wildtype controls ------------------

from screendoor.assaylib.skeletonization._knockout._controls import (  # noqa: E402
    Controls,
    rank_pvalue,
    t_cdf,
    t_quantile,
)


def control_judge(kw, controls, replicates):
    """The detectable-loss judge on a candidate's replicate scores, and a
    summary of the controls with its threshold."""
    c = Controls(kw, controls)
    alpha = kw.get("alpha", 0.05)
    threshold = c.threshold("detectable_loss", alpha, replicates)

    def judge(scores):
        return c.accepts(scores, "detectable_loss", alpha)

    return judge, {**c.summary(), "threshold": threshold}


@pytest.mark.parametrize(
    "p,df,want",
    [
        (0.95, 1, 6.3138),
        (0.95, 39, 1.6849),
        (0.975, 10, 2.2281),
        (0.99, 5, 3.3649),
        (0.05, 39, -1.6849),
        (0.5, 7, 0.0),
    ],
)
def test_t_quantile_matches_tables(p, df, want):
    assert t_quantile(p, df) == pytest.approx(want, abs=1e-4)
    assert t_cdf(t_quantile(p, df), df) == pytest.approx(p, abs=1e-12)


def test_rank_pvalue_is_exact():
    controls = [float(c) for c in range(40)]
    # one candidate: p = (1 + controls at or below it) / 41
    assert rank_pvalue([-1.0], controls) == pytest.approx(1 / 41)
    assert rank_pvalue([9.5], controls) == pytest.approx(11 / 41)
    assert rank_pvalue([99.0], controls) == 1.0
    # several: against every ordering of 3 candidates among 5 controls
    controls = [0.0, 1.0, 2.0, 3.0, 4.0]
    for scores in ([-1.0, 0.5, 1.5], [0.5, 2.5, 3.5], [-2.0, -1.0, 9.0]):
        u = sum(c <= x for x in scores for c in controls)
        us = [
            sum(sum(c < p for c in range(8) if c not in pos) for p in pos)
            for pos in itertools.combinations(range(8), 3)
        ]
        want = sum(v <= u for v in us) / len(us)
        assert rank_pvalue(scores, controls) == pytest.approx(want)


@pytest.mark.parametrize("test", ["mean", "t", "rank"])
def test_identical_controls_make_any_loss_a_loss(test):
    judge, info = control_judge({"control_test": test}, [1.25] * 40, 1)
    assert info["sd"] == 0
    assert judge([1.25]) and judge([1.3])
    assert not judge([1.25 - 1e-9])
    assert not judge([-5.0])


def test_t_threshold_is_a_prediction_bound():
    controls = [0.9, 1.0, 1.1, 1.0, 0.95, 1.05, 1.0, 1.0]
    judge, info = control_judge({}, controls, 2)
    s = info["sd"]
    bound = 1.0 - t_quantile(0.95, 7) * s * (1 / 8 + 1 / 2) ** 0.5
    assert info["test"] == "t" and info["threshold"] == pytest.approx(bound)
    assert judge([bound + 1e-9] * 2) and not judge([bound - 1e-6] * 2)
    # a tolerance lowers the bound by the margin
    _, tol = control_judge({"abs_tol": 0.1}, controls, 2)
    assert tol["threshold"] == pytest.approx(bound - 0.1)


def test_rank_test_shifts_by_the_tolerance():
    controls = [float(c) for c in range(40)]
    judge, info = control_judge({"control_test": "rank"}, controls, 1)
    assert not judge([-1.0]) and not judge([0.5])  # p = 1/41, 2/41
    assert judge([1.5])  # p = 3/41 > 0.05
    judge, _ = control_judge(
        {"control_test": "rank", "abs_tol": 2.0}, controls, 1
    )
    assert judge([-0.5])  # ranked as 1.5


@pytest.mark.parametrize(
    "kw,controls,reps",
    [
        # smallest p is 1/11
        ({"control_test": "rank"}, [float(c) for c in range(10)], 1),
        ({"control_test": "t"}, [1.0], 1),
        ({"control_test": "z"}, [1.0] * 4, 1),
        ({"alpha": 0}, [1.0] * 4, 1),
    ],
)
def test_control_judge_rejects_bad_settings(kw, controls, reps):
    with pytest.raises(ValueError):
        control_judge(kw, controls, reps)


def _competition(essential, cost=0.3, sd=0.02):
    """A fake wildtype competition: the knocked-out essential sites' cost
    plus noise, reproducible from the trial's key."""

    def fake(t):
        rng = random.Random(json.dumps(t["key"], sort_keys=True))
        lost = essential - decode_sites(t["env"]["retained"])
        return -cost * len(lost) + rng.gauss(0.0, sd)

    return fake


@pytest.mark.parametrize("test", ["t", "rank"])
@pytest.mark.parametrize("policy", POLICIES)
def test_noisy_scores_judged_against_controls(policy, test):
    essential = frozenset({0, 1, 2, 10, 44})
    r = simulate_dispatch(
        f"scd.assaylib.skeletonization.{policy}",  # 40 controls by default
        _kwargs(policy, 45, batch_size=8, search_seed=3, control_test=test),
        fake_trial=_competition(essential),
    )
    s = r["completed"]["summary"]
    assert r["completed"]["outcome"] == "succeeded", r["completed"]
    kept = decode_sites(s["retained"])
    assert essential <= kept and s["certified"]
    assert len(kept) <= len(essential) + 3  # a few false alarms at 5%
    control = s["control"]
    assert control["test"] == test and control["n"] == 40
    assert abs(control["mean"]) < 0.02 and 0.01 < control["sd"] < 0.03
    if test == "t":
        assert -0.07 < control["threshold"] < -0.02
    wildtype = [
        t["key"]["replicate"]
        for t in r["trials"]
        if t["key"]["retained"] == "0-44" and "fresh" not in t["key"]
    ]
    assert sorted(wildtype) == list(range(40))
    # all 40 controls go out with the first wave's candidates
    d = {"assay_kwargs": _kwargs(policy, 45), "meta_seed": 3}
    launch, _ = getattr(skeletonization, policy).churn(d, [], [], [])
    keys = [t["key"] for t in launch["kwargs"]["trials"]]
    assert sum(k["retained"] == "0-44" for k in keys) == 40
    assert 40 < len(keys) <= 40 + 8  # ddmin's first wave is two halves


def test_one_control_is_the_mean_rule():
    """With one control, the wildtype's score less the tolerance is the
    threshold. Controls and candidate replicates are counted apart."""
    churn = (
        "scd.assaylib.skeletonization.ddmin.make_churn(num_control_trials=1)"
    )
    r = simulate_dispatch(
        churn,
        {"n_sites": 8, "cmd": "x", "replicates": 2},
        fake_trial=lambda t: {
            "accept": 2 in decode_sites(t["env"]["retained"])
        },
    )
    s = r["completed"]["summary"]
    wildtype = [t for t in r["trials"] if t["key"]["retained"] == "0-7"]
    assert len(wildtype) == 1 and "control" not in s  # accept results
    assert {t["key"]["replicate"] for t in r["trials"]} == {0, 1}
    r = simulate_dispatch(
        churn,
        {"n_sites": 8, "cmd": "x", "rel_tol": 0.1},
        fake_trial=lambda t: float(2 in decode_sites(t["env"]["retained"])),
    )
    assert r["completed"]["summary"]["control"] == {
        "test": "mean",
        "n": 1,
        "mean": 1.0,
        "threshold": 0.9,
    }


def test_trials_get_the_wildtype_sequence():
    seen = set()

    def fake(t):
        seen.add(t["env"]["wildtype"])
        return {"accept": "c" in t["env"]["sequence"]}

    simulate_dispatch(
        "scd.assaylib.skeletonization.ddmin",
        {"sequence": "abcd", "cmd": "x"},
        fake_trial=fake,
    )
    assert seen == {"abcd"}


# -- noninferiority: screen on one replicate, then confirm -----------------


def test_rank_upper_pvalue_is_exact():
    controls = [0.0, 1.0, 2.0, 3.0, 4.0]
    for scores in ([4.5, 3.5, 9.0], [0.5, 2.5, 3.5], [-2.0, -1.0, 9.0]):
        u = sum(c < x for x in scores for c in controls)
        us = [
            sum(sum(c < p for c in range(8) if c not in pos) for p in pos)
            for pos in itertools.combinations(range(8), 3)
        ]
        want = sum(v >= u for v in us) / len(us)
        assert rank_pvalue(scores, controls, upper=True) == pytest.approx(want)
    # one candidate above all 40 controls: p = 1/41
    assert rank_pvalue([99.0], list(map(float, range(40))), upper=True) == (
        pytest.approx(1 / 41)
    )


def test_noninferior_and_loss_bounds_mirror_each_other():
    scores = [0.01 * (-1) ** r for r in range(40)]
    c = Controls({"abs_tol": 0.03}, scores)
    q = t_quantile(0.95, 39) * c.se(4)
    assert c.threshold("detectable_loss", 0.05, 4) == pytest.approx(-0.03 - q)
    assert c.threshold("noninferiority", 0.05, 4) == pytest.approx(-0.03 + q)
    assert c.accepts([-0.02] * 4, "noninferiority", 0.05)
    assert not c.accepts([-0.025] * 4, "noninferiority", 0.05)
    assert c.accepts([-0.035] * 4, "detectable_loss", 0.05)
    # rank: shifted up by the margin, then shown to beat the controls
    r = Controls({"abs_tol": 0.03, "control_test": "rank"}, scores)
    assert r.accepts([0.02] * 4, "noninferiority", 0.05)
    assert not r.accepts([-0.03] * 4, "noninferiority", 0.05)
    assert r.accepts([-0.03] * 4, "detectable_loss", 0.05)
    # identical controls: no noise, so every rule is "at least the limit"
    flat = Controls({}, [0.0] * 40)
    for rule in ("detectable_loss", "noninferiority"):
        assert flat.accepts([0.0], rule, 0.05)
        assert not flat.accepts([-1e-9], rule, 0.05)


def _parity(costs):
    """A fake competition: a genotype's summed cost, plus +0.01 on even
    replicates and -0.01 on odd ones, so controls have mean 0 and sd 0.0101,
    a screen (replicate 0) reads cost - 0.01 high, and 4 confirmations
    average to exactly -cost."""

    def fake(t):
        kept = decode_sites(t["env"]["retained"])
        cost = sum(c for i, c in costs.items() if i not in kept)
        return -cost + (0.01 if t["key"]["replicate"] % 2 == 0 else -0.01)

    return fake


NONINFERIOR = {
    "search_rule": "noninferiority",
    "abs_tol": 0.03,
    "replicates": 4,
    "batch_size": 8,
    "search_seed": 5,
}
# essential sites fail the screen; each mild one (0.03) fails the
# noninferiority confirmation (accepts up to 0.021) but passes the sweep's
# pass's loss confirmation (accepts up to 0.039); two mild ones (0.06)
# fail the screen (rejects above 0.057)
COSTS = {0: 0.5, 1: 0.5, 5: 0.03, 6: 0.03}


@pytest.mark.parametrize("policy", POLICIES)
def test_noninferiority_search_then_detectable_loss_sweep(policy):
    r = simulate_dispatch(
        f"scd.assaylib.skeletonization.{policy}",
        _kwargs(policy, 12, **NONINFERIOR),
        fake_trial=_parity(COSTS),
    )
    assert r["completed"]["outcome"] == "succeeded", r["completed"]
    s = r["completed"]["summary"]
    kept = decode_sites(s["retained"])
    assert s["certified"]
    # the search keeps both mild sites; the final pass drops one of them
    assert len(kept) == 3 and {0, 1} <= kept and len(kept & {5, 6}) == 1
    control = s["control"]
    assert control["margin"] == pytest.approx(0.03)
    stages = control["stages"]
    assert stages["screen"]["threshold"] == pytest.approx(-0.04728, abs=1e-4)
    assert stages["search"]["rule"] == "noninferiority"
    assert stages["search"]["threshold"] == pytest.approx(-0.02105, abs=1e-4)
    assert stages["sweep"]["rule"] == "detectable_loss"
    assert stages["sweep"]["threshold"] == pytest.approx(-0.03895, abs=1e-4)
    assert all(st["harmless_pass_rate"] > 0.99 for st in stages.values())
    tally = control["verdicts"]
    assert tally["search_screen_reject"] > 0
    assert tally["search_noninferiority_accept"] > 0
    assert tally["search_noninferiority_reject"] > 0
    assert tally["sweep_detectable_loss_accept"] >= 1
    # a screened-out genotype ran once; one that passed ran 1 + 4 times
    by_genotype = {}
    for t in r["trials"]:
        k = t["key"]
        g = (k["retained"], k.get("fresh", 0))
        by_genotype.setdefault(g, set()).add(k["replicate"])
    for (retained, _), reps in by_genotype.items():
        if retained == "0-11":
            continue  # the controls
        lost = sum(COSTS.get(i, 0) for i in range(12)) - sum(
            COSTS.get(i, 0) for i in decode_sites(retained)
        )
        assert reps == ({0} if lost > 0.0573 else {0, 1, 2, 3, 4}), retained


@pytest.mark.parametrize("policy", ["ddmin", "gama"])
def test_noninferiority_throughout(policy):
    r = simulate_dispatch(
        f"scd.assaylib.skeletonization.{policy}",
        _kwargs(policy, 12, sweep_rule="noninferiority", **NONINFERIOR),
        fake_trial=_parity(COSTS),
    )
    s = r["completed"]["summary"]
    assert decode_sites(s["retained"]) == {0, 1, 5, 6} and s["certified"]
    assert s["control"]["stages"]["sweep"]["rule"] == "noninferiority"
    assert not any("detectable" in k for k in s["control"]["verdicts"])


def test_noninferiority_with_identical_controls_counts_any_loss():
    costs = {0: 0.5, 3: 1e-6}  # site 3's loss is tiny, but real
    r = simulate_dispatch(
        "scd.assaylib.skeletonization.ddmin",
        {
            "n_sites": 8,
            "cmd": "x",
            "search_rule": "noninferiority",
            "replicates": 2,
        },
        fake_trial=lambda t: -sum(
            c
            for i, c in costs.items()
            if i not in decode_sites(t["env"]["retained"])
        ),
    )
    s = r["completed"]["summary"]
    assert decode_sites(s["retained"]) == {0, 3}
    assert s["control"]["sd"] == 0
    assert s["control"]["stages"]["search"]["harmless_pass_rate"] == 1


@pytest.mark.parametrize(
    "kw,fake,reason",
    [
        ({}, _parity({0: 0.5}), "needs a margin"),
        ({"abs_tol": 0.03}, lambda t: {"accept": True}, "needs scores"),
        ({"abs_tol": 0.03, "sweep_rule": "maybe"}, _parity({}), "one of"),
        ({"abs_tol": 0.03, "search_rule": None}, _parity({}), "one of"),
    ],
)
def test_noninferiority_refuses_bad_settings(kw, fake, reason):
    r = simulate_dispatch(
        "scd.assaylib.skeletonization.ddmin",
        {"n_sites": 8, "cmd": "x", "search_rule": "noninferiority", **kw},
        fake_trial=fake,
        churn_maxretry=0,
    )
    assert r["completed"]["outcome"] == "failed"
    assert reason in r["completed"]["reason"]


@pytest.mark.parametrize("final_audit", [True, False])
@pytest.mark.parametrize("policy", POLICIES)
def test_null_sweep_rule_skips_the_sweep(policy, final_audit):
    r = simulate_dispatch(
        f"scd.assaylib.skeletonization.{policy}",
        _kwargs(
            policy,
            12,
            sweep_rule=None,
            final_audit=final_audit,
            **NONINFERIOR,
        ),
        fake_trial=_parity(COSTS),
    )
    s = r["completed"]["summary"]
    assert r["completed"]["outcome"] == "succeeded"
    assert not s["certified"] and s["status"] == "sweep_skipped"
    kept = decode_sites(s["retained"])
    assert {0, 1, 5, 6} <= kept  # noninferiority alone keeps the mild sites
    if policy in ("minesweeper", "gama"):  # they screen single sites
        assert kept == {0, 1, 5, 6}
    else:  # ddmin stops at chunks of two, leaving the rest to the sweep
        assert len(kept) > 4
    control = s["control"]
    assert not control["sweep"] and "sweep" not in control["stages"]
    # the final audit alone, by the search's rule
    audited = any("fresh" in t["key"] for t in r["trials"])
    assert audited == final_audit
    sweep = {k for k in control["verdicts"] if k.startswith("sweep_")}
    assert sweep == ({"sweep_noninferiority_accept"} if final_audit else set())
    assert all(t["reason"] != "certified_proposal" for t in s["transitions"])


def test_gama_without_sweep_stops_after_mate():
    pred = _pred(frozenset({0, 1, 2, 10, 44}))
    search = _gama(45, seed=3, sweep=False)
    result, waves = _drive(search, pred)
    assert result["status"] == "sweep_skipped"
    assert [t[3] for t in result["transitions"]] == ["gama"]
    assert len(result["retained"]) == 45 - search.stats["deleted"]["mate"]


@pytest.mark.parametrize(
    "policy,rule",
    [
        *((policy, "noninferiority") for policy in POLICIES),
        ("ddmin", "sprt"),
        ("ddmin", "mixture"),
    ],
)
def test_detectable_loss_search_then_noninferiority_sweep(policy, rule):
    """The search commits a mild deletion; the sweep's noninferiority
    audit rejects that skeleton, rolls it back, and keeps both mild sites."""
    kw = {
        **NONINFERIOR,
        "search_rule": "detectable_loss",
        "sweep_rule": rule,
    }
    r = simulate_dispatch(
        f"scd.assaylib.skeletonization.{policy}",
        _kwargs(policy, 12, **kw),
        fake_trial=_parity(COSTS),
    )
    s = r["completed"]["summary"]
    assert decode_sites(s["retained"]) == {0, 1, 5, 6} and s["certified"]
    assert s["rollbacks"] == 1
    tally = s["control"]["verdicts"]
    assert tally["search_detectable_loss_accept"] > 0
    capped = tally.get(f"sweep_{rule}_capped", 0)  # undecided: kept, too
    assert tally.get(f"sweep_{rule}_reject", 0) + capped > 0


# -- sequential rules: sprt and mixture -------------------------------------

from statistics import NormalDist  # noqa: E402

from screendoor.assaylib.skeletonization._knockout._SequentialTest import (  # noqa: E402
    SequentialTest,
)
from screendoor.assaylib.skeletonization._knockout._controls import (  # noqa: E402
    chi2_quantile,
)


@pytest.mark.parametrize(
    "p,df,want",
    [
        (0.95, 1, 3.8415),
        (0.05, 10, 3.9403),
        (0.01, 30, 14.9535),
        (0.025, 39, 23.6543),
        (0.95, 100, 124.3421),
    ],
)
def test_chi2_quantile_matches_tables(p, df, want):
    assert chi2_quantile(p, df) == pytest.approx(want, abs=1e-4)


def _sequential(**kw):
    """A SequentialTest on 40 controls of mean 0 and sd 0.0101, with a
    margin of 0.03, and those controls."""
    kw = {"abs_tol": 0.03, **kw}
    c = Controls(kw, [0.01 * (-1) ** r for r in range(40)])
    return SequentialTest(kw, c, 12), c


def test_sequential_test_bounds_the_wildtype_mean_and_sd():
    t, c = _sequential()
    shift = t_quantile(1 - 0.05 / 8, 39) * c.sd / 40**0.5
    assert t.limit == pytest.approx(c.limit + shift) and shift > 0
    assert t.sd_bound == pytest.approx(
        c.sd * (39 / chi2_quantile(0.05 / 8, 39)) ** 0.5
    )
    assert 1.3 * c.sd < t.sd_bound < 1.5 * c.sd
    assert t.gap == pytest.approx(0.4 * (c.mean - t.limit))
    # a relative tolerance scales the wildtype's mean, and so its bound
    scores = [1 + x for x in c.scores]
    kw = {"rel_tol": 0.1, "indifference": 1.0}
    r = SequentialTest(kw, Controls(kw, scores), 12)
    assert r.limit == pytest.approx(0.9 * (1 + shift))
    assert r.gap == pytest.approx(1 - r.limit)


def test_sequential_alphas_never_overspend():
    t, _ = _sequential(planned_tests=10, error_rate=0.08)
    alphas = [t.alpha(i) for i in range(10 * (2**12 - 1))]
    assert alphas[:10] == [0.06 / 20] * 10  # the first share half
    assert alphas[10:30] == [0.06 / 80] * 20  # twice as many, a quarter
    assert alphas[30] == pytest.approx(0.06 / 320)
    assert 0.0599 < sum(alphas) < 0.06  # of error_rate, 3/4 is the tests'
    assert _sequential()[0].planned_tests == 8 * 12


def test_sprt_is_the_gaussian_likelihood_ratio():
    t, _ = _sequential()
    null = NormalDist(t.limit, t.sd_bound)
    alternative = NormalDist(t.limit + t.gap, t.sd_bound)
    rng = random.Random(1)
    for mean in (t.limit - 0.01, t.limit, t.limit + t.gap, 0.0):
        scores = [rng.gauss(mean, 0.01) for _ in range(40)]
        ratio, want = 0.0, None
        for n, x in enumerate(scores, 1):
            ratio += math.log(alternative.pdf(x) / null.pdf(x))
            if want is None and ratio >= math.log(1 / 0.001):
                want = "accept"
            if want is None and ratio <= math.log(t.futility):
                want = "reject"
            assert t.judge(scores[:n], "sprt", 0.001) == want
    assert t.judge([0.0] * 40, "sprt", 0.001) == "accept"
    assert t.judge([-0.03] * 40, "sprt", 0.001) == "reject"


def test_mixture_boundary_is_where_the_mixture_martingale_is_1_over_alpha():
    t, _ = _sequential()
    rho, alpha = (t.sd_bound / t.gap) ** 2, 0.001
    for n in (1, 5, 40):
        lo, hi = 0.0, 1.0  # bisect the total that the n-th score accepts
        for _ in range(60):
            mid = (lo + hi) / 2
            scores = [t.limit] * (n - 1) + [t.limit + mid]
            if t.judge(scores, "mixture", alpha) == "accept":
                hi = mid
            else:
                lo = mid
        z = hi / t.sd_bound
        # mix exp(lambda * z - lambda^2 * n / 2) over lambda ~ N(0, 1/rho)
        prior, step = NormalDist(0.0, rho**-0.5), 1e-4
        martingale = step * sum(
            math.exp(lam * z - lam * lam * n / 2) * prior.pdf(lam)
            for lam in (step * k for k in range(-200000, 200001))
        )
        assert martingale == pytest.approx(1 / alpha, rel=1e-6)
        # and the interval is two-sided: the mirror total rejects
        scores = [t.limit] * (n - 1) + [t.limit - hi * (1 + 1e-9)]
        assert t.judge(scores, "mixture", alpha) == "reject"


@pytest.mark.parametrize("rule", ["sprt", "mixture"])
def test_sequential_rules_keep_their_alpha(rule):
    t, c = _sequential()
    rng = random.Random(2)

    def accepted(mean, sd):
        return sum(
            t.judge([rng.gauss(mean, sd) for _ in range(64)], rule, 0.05)
            == "accept"
            for _ in range(2000)
        )

    # a loss of the whole margin, as noisy as the bound allows
    assert 0 < accepted(t.limit, t.sd_bound) <= 0.05 * 2000
    assert accepted(c.mean, c.sd) > 0.99 * 2000  # no loss


def test_sequential_bounds_hold_over_fresh_controls():
    """A loss of exactly the margin is accepted no more often than
    `error_rate`, counting the controls' luck as well as the test's."""
    rng = random.Random(3)
    kw = {"abs_tol": 0.03, "error_rate": 0.2, "planned_tests": 1}
    accepted = 0
    for _ in range(300):
        controls = [rng.gauss(0.0, 0.01) for _ in range(40)]
        t = SequentialTest(kw, Controls(kw, controls), 12)
        scores = [rng.gauss(-0.03, 0.01) for _ in range(64)]
        accepted += t.judge(scores, "sprt", t.alpha(0)) == "accept"
    assert accepted <= 0.2 * 300


@pytest.mark.parametrize(
    "kw,reason",
    [
        ({"error_rate": 0}, "error_rate"),
        ({"futility": 1}, "futility"),
        ({"indifference": 1.5}, "indifference"),
        ({"max_replicates": 0}, "max_replicates"),
        ({"planned_tests": 0}, "planned_tests"),
        ({"control_test": "rank"}, "control_test 't'"),
        ({"abs_tol": 0.004}, "needs a margin above 0.00419"),
    ],
)
def test_sequential_test_refuses_bad_settings(kw, reason):
    with pytest.raises(ValueError, match=reason):
        _sequential(**kw)
    # and a margin so thin that even a harmless deletion would not pass
    t, _ = _sequential(abs_tol=0.006)
    with pytest.raises(ValueError, match="would not accept"):
        t.summary("sprt")


SEQUENTIAL = {"abs_tol": 0.06, "batch_size": 8, "search_seed": 3}


def _replicates_by_genotype(r):
    by_genotype = {}
    for t in r["trials"]:
        k = t["key"]
        g = (k["retained"], k.get("fresh", 0))
        by_genotype.setdefault(g, set()).add(k["replicate"])
    return by_genotype


@pytest.mark.parametrize(
    "policy,rule",
    [("ddmin", "sprt"), ("hybrid", "sprt"), ("ddmin", "mixture")],
)
def test_sequential_rule_throughout(policy, rule):
    essential = frozenset({0, 1, 2, 10, 29})
    r = simulate_dispatch(
        f"scd.assaylib.skeletonization.{policy}",
        _kwargs(policy, 30, search_rule=rule, sweep_rule=rule, **SEQUENTIAL),
        fake_trial=_competition(essential),
    )
    assert r["completed"]["outcome"] == "succeeded", r["completed"]
    s = r["completed"]["summary"]
    assert decode_sites(s["retained"]) == essential and s["certified"]
    control = s["control"]
    assert control["error_rate"] == 0.05 and control["margin"] == 0.06
    stage = control["stages"]["search"]
    assert control["stages"] == {"search": stage, "sweep": stage}
    assert stage["rule"] == rule and stage["max_replicates"] == 64
    assert -0.06 < stage["limit"] < -0.04
    assert stage["sd_bound"] > control["sd"]
    assert stage["indifference"] == pytest.approx(-0.4 * stage["limit"], 0.2)
    assert 4 < stage["harmless_replicates"] <= 16
    tally = control["verdicts"]
    assert tally[f"search_{rule}_accept"] > 0
    assert tally[f"search_{rule}_reject"] > 0
    # every commit passed within the error rate, so nothing is audited
    by_genotype = _replicates_by_genotype(r)
    assert all(not fresh for _, fresh in by_genotype)
    # looks double: an essential knockout is given up at once, and a
    # harmless one takes several scores to accept
    for (retained, _), reps in by_genotype.items():
        if retained == "0-29":
            continue  # the controls
        assert reps == set(range(len(reps)))
        assert len(reps) in (1, 2, 4, 8, 16, 32, 64)
        if essential <= decode_sites(retained):
            assert len(reps) >= 4, retained
        else:
            assert len(reps) <= 2, retained


def _mild(costs, sd=0.02):
    """A fake wildtype competition: a genotype's summed cost, plus noise
    reproducible from the trial's key."""

    def fake(t):
        rng = random.Random(json.dumps(t["key"], sort_keys=True))
        kept = decode_sites(t["env"]["retained"])
        cost = sum(c for i, c in costs.items() if i not in kept)
        return -cost + rng.gauss(0.0, sd)

    return fake


def test_sprt_keeps_small_losses_from_adding_up():
    """Three sites each cost 0.022: within the 0.06 margin alone, but not
    together. A detectable-loss search deletes all three; sprt stops
    within the margin."""
    costs = {0: 0.5, 1: 0.5, 10: 0.022, 11: 0.022, 12: 0.022}
    lost = {}
    for rule in ("detectable_loss", "sprt"):
        r = simulate_dispatch(
            "scd.assaylib.skeletonization.ddmin",
            {
                "n_sites": 16,
                "cmd": "x",
                "search_rule": rule,
                "sweep_rule": rule,
                "final_audit": False,
                **SEQUENTIAL,
            },
            fake_trial=_mild(costs),
        )
        kept = decode_sites(r["completed"]["summary"]["retained"])
        assert {0, 1} <= kept
        lost[rule] = sum(c for i, c in costs.items() if i not in kept)
    assert lost["detectable_loss"] == pytest.approx(0.066)
    assert 0 < lost["sprt"] <= 0.06


def test_sequential_churn_is_pure_and_replayable():
    kw = {
        "n_sites": 16,
        "cmd": "x",
        "search_rule": "sprt",
        "sweep_rule": "sprt",
        "batch_size": 4,
        "abs_tol": 0.06,
    }
    r = simulate_dispatch(
        "scd.assaylib.skeletonization.ddmin",
        kw,
        fake_trial=_competition(frozenset({3, 9})),
        meta_seed=7,
    )
    d = {
        "assay_kwargs": kw,
        "meta_seed": 7,
        "dispatch_uuid": r["dispatch_uuid"],
    }
    churn = skeletonization.ddmin.churn
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
    # cut off midway, it asks only for trials that were in fact launched
    keys = {json.dumps(t["key"], sort_keys=True) for t in r["trials"]}
    done = {p["trial_uuid"] for p in pays[: len(pays) // 2]}
    launch = churn(d, [x for x in subs if x["trial_uuid"] in done], pays, [])
    assert launch[0]["action"] == "launch"
    asked = launch[0]["kwargs"]["trials"]
    assert asked and all(
        json.dumps(t["key"], sort_keys=True) in keys for t in asked
    )


def test_sprt_search_then_detectable_loss_sweep():
    """The search's streams start after the replicates that the sweep's
    rule judges, and the sweep's skeleton is audited afresh."""
    essential = frozenset({0, 1, 2, 10, 29})
    r = simulate_dispatch(
        "scd.assaylib.skeletonization.ddmin",
        {
            "n_sites": 30,
            "cmd": "x",
            "search_rule": "sprt",
            "replicates": 2,
            **SEQUENTIAL,
        },
        fake_trial=_competition(essential),
    )
    s = r["completed"]["summary"]
    assert decode_sites(s["retained"]) == essential and s["certified"]
    stages = s["control"]["stages"]
    assert stages["search"]["rule"] == "sprt"
    assert stages["sweep"]["rule"] == "detectable_loss"
    assert stages["sweep"]["replicates"] == 2
    tally = s["control"]["verdicts"]
    assert tally["search_sprt_accept"] > 0
    assert tally["sweep_detectable_loss_reject"] >= len(essential)
    by_genotype = _replicates_by_genotype(r)
    assert any(fresh for _, fresh in by_genotype)  # the final audit
    streams = 0
    for (retained, fresh), reps in by_genotype.items():
        if retained == "0-29":
            continue  # the controls
        fixed, stream = reps & {0, 1}, reps - {0, 1}
        assert fixed in (set(), {0, 1})
        assert stream == set(range(2, 2 + len(stream)))
        assert len(stream) in (0, 2, 4, 8, 16, 32, 64)
        assert not (fresh and stream)  # the audit is the sweep's
        streams += bool(stream)
    assert streams == sum(
        v for k, v in tally.items() if k.startswith("search_")
    )


def test_sequential_rule_with_identical_controls_counts_any_loss():
    costs = {0: 0.5, 3: 1e-6}  # site 3's loss is tiny, but real
    r = simulate_dispatch(
        "scd.assaylib.skeletonization.ddmin",
        {
            "n_sites": 8,
            "cmd": "x",
            "search_rule": "sprt",
            "sweep_rule": "sprt",
        },
        fake_trial=lambda t: -sum(
            c
            for i, c in costs.items()
            if i not in decode_sites(t["env"]["retained"])
        ),
    )
    s = r["completed"]["summary"]
    assert decode_sites(s["retained"]) == {0, 3}
    stage = s["control"]["stages"]["search"]
    assert stage["sd_bound"] == 0 and stage["harmless_replicates"] == 1
    assert all(
        reps == {0}
        for (retained, _), reps in _replicates_by_genotype(r).items()
        if retained != "0-7"
    )


def test_sequential_final_audit_is_opt_in():
    r = simulate_dispatch(
        "scd.assaylib.skeletonization.ddmin",
        {
            "n_sites": 12,
            "cmd": "x",
            "search_rule": "mixture",
            "sweep_rule": None,
            "final_audit": True,
            **SEQUENTIAL,
        },
        fake_trial=_competition(frozenset({0, 1})),
    )
    s = r["completed"]["summary"]
    assert s["status"] == "sweep_skipped" and {0, 1} <= decode_sites(
        s["retained"]
    )
    assert any(fresh for _, fresh in _replicates_by_genotype(r))
    assert s["control"]["verdicts"]["sweep_mixture_accept"] == 1


@pytest.mark.parametrize(
    "kw,fake,reason",
    [
        ({"sweep_rule": "noninferiority"}, _parity({}), "goes with"),
        ({"sweep_rule": "mixture"}, _parity({}), "goes with"),
        ({"control_test": "rank"}, _parity({}), "control_test"),
        ({"abs_tol": 0}, _parity({}), "needs a margin"),
        ({"abs_tol": 0.006}, _parity({}), "would not accept"),
        ({}, lambda t: {"accept": True}, "needs scores"),
        ({"replicates": 4, "max_replicates": 2}, _parity({}), "at least"),
    ],
)
def test_sequential_rule_refuses_bad_settings(kw, fake, reason):
    r = simulate_dispatch(
        "scd.assaylib.skeletonization.ddmin",
        {
            "n_sites": 8,
            "cmd": "x",
            "search_rule": "sprt",
            "sweep_rule": "sprt",
            "abs_tol": 0.03,
            **kw,
        },
        fake_trial=fake,
        churn_maxretry=0,
    )
    assert r["completed"]["outcome"] == "failed"
    assert reason in r["completed"]["reason"]
