import asyncio
import itertools
import os
import random
import sys

import pytest

from screendoor.assaylib import skeletonization
from screendoor.assaylib.skeletonization._engine._codec import (
    decode_sites,
    encode_sites,
)
from screendoor.auxlib._DispatchContext import load_dispatches
from screendoor.testing import simulate_dispatch

OLD = os.path.expanduser("~/2026-11-03")
POLICIES = ["ddmin", "minesweeper", "hybrid"]


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


def _sim(policy, n, pred, **kw):
    return simulate_dispatch(
        f"scd.assaylib.skeletonization.{policy}",
        {"n_sites": n, "cmd": "x", **kw},
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
    r = _sim(policy, 16, pred, batch_size=4)
    d = {
        "assay_kwargs": {"n_sites": 16, "cmd": "x", "batch_size": 4},
        "meta_seed": 1,
        "dispatch_uuid": r["dispatch_uuid"],
    }
    churn = getattr(skeletonization, policy).churn
    (ctx,) = load_dispatches(r["workdir"])
    subs, pays = ctx.read_trial_submissions(), ctx.read_trial_payloads()
    a1 = churn(d, subs, pays, [])
    a2 = churn(d, subs[::-1], pays[::-1], [])
    assert a1 == a2  # independent of record order


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
    assert {t["key"]["rep"] for t in r["trials"]} == {0, 1}


def test_trial_failure_fails_dispatch_or_rejects():
    def fake(t):
        if "7" not in t["env"]["knockout"].replace("-", ",").split(","):
            return {"accept": True}
        raise RuntimeError("simulator crashed")

    r = simulate_dispatch(
        "scd.assaylib.skeletonization.ddmin",
        {"n_sites": 8, "cmd": "x"},
        fake_trial=fake,
    )
    assert r["completed"]["outcome"] == "failed"
    assert "simulator crashed" in r["completed"]["reason"]
    r = simulate_dispatch(
        "scd.assaylib.skeletonization.ddmin",
        {"n_sites": 8, "cmd": "x", "on_trial_failure": "reject"},
        fake_trial=fake,
    )
    assert r["completed"]["outcome"] == "succeeded"


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
    assert {"g": "0-15", "rep": 0} in keys  # wildtype reference
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
            POLICIES,
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
