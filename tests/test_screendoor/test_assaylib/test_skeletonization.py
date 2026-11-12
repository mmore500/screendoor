import asyncio
import itertools
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
    assert {t["key"]["replicate"] for t in r["trials"]} == {0, 1}


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
    assert {"retained": "0-15", "replicate": 0} in keys  # wildtype
    assert len(keys) == 9
    assert progress["action"] == "progress"


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
