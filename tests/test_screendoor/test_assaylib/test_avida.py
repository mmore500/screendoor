"""The knockout policies on real Avida, through the real worker and the
devosoft/avida container."""

import asyncio
import json
import os
import shutil
import sys

import pytest

from screendoor.auxlib import decode_sites
from screendoor.testing import simulate_dispatch

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), *[".."] * 3))
sys.path.insert(0, os.path.join(REPO, "examples", "avida"))
from make_dispatch import make_dispatch  # noqa: E402

pytestmark = [
    pytest.mark.heavy,
    pytest.mark.skipif(
        shutil.which("singularity") is None, reason="needs singularity"
    ),
]

EXPECTED = {  # minimal skeletons from the 2026-11-03 benchmark report
    "default_heads_50": "wzcagcAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAzvfcaxgab",
    "nand_50": "wzcagcAAAAyycuyAAAAAAAAAAAAAAAAAAAAAAAAAAzvfcaxgab",
}

# the original knockout_skeleton experiments, and the Avida they were run on
OLD = os.path.expanduser("~/2026-11-03")
OLD_BINARY = os.environ.get(
    "AVIDA_BINARY", os.path.join(OLD, "build/avida/bin/avida")
)


def run(organism, policy, seed=42, **assay_kwargs):
    d = make_dispatch(
        organism, policy=policy, search_seed=seed, assay_kwargs=assay_kwargs
    )
    return simulate_dispatch(d["assay"], d["assay_kwargs"], trial_batchsize=1)


@pytest.mark.parametrize("policy", ["ddmin", "minesweeper", "hybrid"])
@pytest.mark.parametrize("organism", sorted(EXPECTED))
def test_known_skeletons(organism, policy):
    r = run(organism, policy)
    assert r["completed"]["outcome"] == "succeeded", r["completed"]
    s = r["completed"]["summary"]
    assert s["certified"]
    assert s["skeleton"] == EXPECTED[organism]


@pytest.mark.parametrize("organism", sorted(EXPECTED))
def test_gama_known_skeletons(organism):
    """GAMA with small populations: the paper's sizes are for a cluster."""
    r = run(
        organism,
        "gama",
        guess_subsets=16,
        add_combinations=32,
        elite_size=8,
        mate_children=24,
        mate_patience=3,
    )
    assert r["completed"]["outcome"] == "succeeded", r["completed"]
    s = r["completed"]["summary"]
    assert s["certified"]
    assert s["skeleton"] == EXPECTED[organism]
    by_stage = s["stats"]["deleted"]
    assert by_stage["guess"] < by_stage["add"] <= by_stage["mate"]


@pytest.mark.skipif(
    not os.path.isdir(os.path.join(OLD, "knockout_skeleton"))
    or not os.path.exists(OLD_BINARY),
    reason="needs ~/2026-11-03/knockout_skeleton and its Avida binary",
)
@pytest.mark.parametrize("policy", ["ddmin", "minesweeper", "hybrid"])
@pytest.mark.parametrize(
    "organism", ["redundant_nand_50", "small_effect_vb_50", "evolved_9task_67"]
)
def test_matches_original_on_avida(organism, policy):
    sys.path.insert(0, OLD)
    from knockout_skeleton import ExactEvaluator, SearchConfig, skeletonize
    from knockout_skeleton.avida import AvidaExactOracle

    oracle = AvidaExactOracle(
        organism, rel_fitness_tol=0.02, binary_path=OLD_BINARY
    )
    ref = asyncio.run(
        skeletonize(
            oracle.organism.wildtype_genome,
            ExactEvaluator(oracle, max_parallel=8),
            SearchConfig(policy=policy, batch_size=8, seed=42),
        )
    )
    r = run(organism, policy)
    s = r["completed"]["summary"]
    assert decode_sites(s["retained"]) == ref.retained
    assert s["proposal_batches"] == ref.proposal_batches
    assert s["skeleton"] == oracle.organism.to_sequence(ref.retained)
    # every trial really ran Avida and reported Test CPU metrics
    t = r["trials"][0]
    assert set(t["result"]) >= {"score", "viable", "tasks"}
    assert json.dumps(s)
