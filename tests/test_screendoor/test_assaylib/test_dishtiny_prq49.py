import collections
import json
import os
import random
import sys

import pytest

from screendoor.assaylib.dishtiny_prq49 import (
    e2e_skeleton,
    run_trial,
    units_of,
)
from screendoor.assaylib.dishtiny_prq49._compete import (
    Inconclusive,
    compete,
    diverges,
    knocked_out,
)
from screendoor.auxlib import decode_sites
from screendoor.testing import simulate_dispatch

# a toy program: each instruction's operation, and what knocking it out
# does. `dead` is provably so, to the pruner; `silent` changes nothing a
# competition shows; `cheap` changes the world at no cost; `sly` does
# too, but not a world of its own, so the side-by-side test passes it;
# `late` costs a little at the small size and too much at the full;
# `critical` is lethal. `after:15` is dead once position 15 is out.
TOY = [
    ("Global Anchor", "critical"),  # 0
    ("Terminal", "critical"),
    ("Write Own State", "critical"),
    ("Add", "dead"),
    ("Nop-0", None),
    ("Global Anchor", "silent"),  # 5: a module of silent content
    ("Read Own State", "silent"),
    ("Send Intra-Cell Message", "silent"),
    ("Global Anchor", "cheap"),  # 8: a module of cheap content
    ("Add To Own State", "cheap"),
    ("Multiply", "cheap"),
    ("Local Anchor", "cheap"),
    ("Global Anchor", "critical"),  # 12: a mixed module
    ("Send Inter-Cell Message", "critical"),
    ("Bitwise Xor", "sly"),
    ("Adjust Global Regulator", "cheap"),
    ("Local Jump If", "cheap"),
    ("Subtract", "after:15"),
    ("RandomFill", "silent"),
    ("Local Anchor", "late"),
]
OPERATIONS = [o for o, _ in TOY]
EFFECT = {p: e for p, (_, e) in enumerate(TOY) if e is not None}
SKELETON = {0, 1, 2, 12, 13, 19}
KW = {
    "operations": OPERATIONS,
    "num_control_trials": 40,
    "num_full_control_trials": 20,
    "final_replicates": 8,
    "num_screen_control_trials": 20,
    "env": {"DISHTINY_BINARY": "rundishtiny"},
}


def dead(position, knockout):
    effect = EFFECT[position]
    return effect == "dead" or (
        effect.startswith("after:") and int(effect[6:]) in knockout
    )


def fake_trial(t, strip_fails=False):
    env = t["env"]
    assert env["DISHTINY_BINARY"] == "rundishtiny"
    knockout = decode_sites(env["DISHTINY_KNOCKOUT"])
    worlds = json.loads(env.get("DISHTINY_WORLDS", "null"))
    mode = env["DISHTINY_MODE"]
    effects = collections.Counter(
        "dead" if dead(p, knockout) else EFFECT[p] for p in knockout
    )
    if mode == "strip":
        assert not strip_fails and worlds is None
        return {
            "pruned": sorted(
                p for p in EFFECT if p not in knockout and dead(p, knockout)
            )
        }
    if mode == "identity":
        # the search's test is the side-by-side one alone; an audit's is
        # also by competition, on worlds of its own
        assert [d[:2] for d in json.loads(env["DISHTINY_DIVERGENCE"])] == [
            [2048, 100],
            [8192, 100],
        ]
        audit = "fresh" in t["key"]["key"]
        assert bool(worlds) == audit
        same = {"dead", "silent"} if audit else {"dead", "silent", "sly"}
        return {"accept": set(effects) <= same}
    size = (env["DISHTINY_UPDATES"], env["DISHTINY_N_CELLS"])
    rng = random.Random(json.dumps(t["key"], sort_keys=True))
    if mode == "screen" or size == ("8192", "576"):
        # a lethal knockout dies out; any other holds about half the cells
        assert size == ("8192", "576") and worlds is None
        share = 0.0 if effects["critical"] else 0.5 + rng.gauss(0.0, 0.1)
        if mode == "score":
            return {"score": share}
        return {
            "score": share,
            "accept": share > float(env["DISHTINY_SCREEN_PASS"]),
        }
    assert mode == "score" and size in (("12288", "36"), ("24576", "1024"))
    late = (0.3 if size[1] == "1024" else 0.04) * effects["late"]
    lost = 0.5 * bool(effects["critical"]) + late
    return {"score": 0.5 - lost + rng.gauss(0.0, 0.02)}


def test_units_of():
    units, labels = units_of("modules", OPERATIONS)
    assert units == [[1, 2, 3], [6, 7], [9, 10, 11], list(range(13, 20))]
    assert labels[0] == "module@0(3)" and labels[3] == "module@12(7)"
    assert units_of("outputs", OPERATIONS)[0] == [[2], [7], [9], [13], [15]]
    # calculations are the rest, less global anchors: local anchors,
    # inputs and control flow among them
    calculations, labels = units_of("calculations", OPERATIONS)
    assert [u for (u,) in calculations] == [
        *(1, 3, 6, 10, 11, 14),
        *(16, 17, 18, 19),
    ]
    assert "Local Anchor@11" in labels and "Read Own State@6" in labels
    everything, labels = units_of("all", OPERATIONS)
    assert len(everything) == 19 and "Global Anchor@12" in labels
    # knocked-out positions are not live, and a module without its
    # anchor joins the module before
    out = frozenset({6, 7, 9, 10, 11})
    assert [u for (u,) in units_of("all", OPERATIONS, out)[0]] == [
        *(0, 1, 2, 3, 5, 8),
        *range(12, 20),
    ]
    assert units_of("modules", OPERATIONS, out)[0] == [
        [1, 2, 3],
        list(range(13, 20)),
    ]
    merged, labels = units_of("modules", OPERATIONS, frozenset({5}))
    assert merged[0] == [1, 2, 3, 6, 7] and labels[0] == "module@0(5)"
    # ahead of the first live anchor, content wraps around to the last
    wrapped, labels = units_of("modules", OPERATIONS, frozenset({0}))
    assert wrapped[-1] == [1, 2, 3, *range(13, 20)]
    # with no anchor at all, the program is one module
    bare = ["Add", "Nop-0", "Terminal"]
    assert units_of("modules", bare) == ([[0, 2]], ["module@0(2)"])
    with pytest.raises(ValueError):
        units_of("anchors", OPERATIONS)


def test_knocked_out_keeps_the_random_number_stream():
    genome = {
        "value0": {
            "program": [
                {
                    "operation": o,
                    "args": {},
                    "bitstring": "0",
                    "descriptors": [1],
                }
                for o in ("Add", "RandomFill", "Draw Random Value", "Nop-0")
            ]
        },
        "value1": 7,
    }
    out = knocked_out(genome, {0, 1, 2})
    ops = [x["operation"] for x in out["value0"]["program"]]
    assert ops == ["Nop-0", "Nop-1", "Nop-2", "Nop-0"] and out["value1"] == 7
    assert all(x["descriptors"] == [] for x in out["value0"]["program"])
    assert genome["value0"]["program"][0]["operation"] == "Add"
    same = knocked_out(genome, set())["value0"]["program"]
    assert [x["operation"] for x in same][:2] == ["Add", "RandomFill"]


def test_e2e_skeleton():
    r = simulate_dispatch(
        "scd.assaylib.dishtiny_prq49.e2e_skeleton",
        KW,
        fake_trial=fake_trial,
        meta_seed=1,
    )
    assert r["completed"]["outcome"] == "succeeded", r["completed"]
    s = r["completed"]["summary"]
    assert decode_sites(s["skeleton"]) == SKELETON
    assert s["skeleton_count"] == 6 and s["knockout_count"] == 13
    stages = {x["stage"].partition(":")[2]: x for x in s["stages"]}
    assert [x["stage"] for x in s["stages"]] == [
        f"{i:02d}:{spec}" for i, spec in enumerate(e2e_skeleton.STAGES)
    ]
    assert [m["stage"] for m in r["memo"]] == [x["stage"] for x in s["stages"]]
    # the first strip takes the dead code; identity takes the silent
    # module, then the silent calculation, then the module's anchor
    assert s["stages"][0]["summary"]["pruned"] == [3]
    assert stages["identity:modules"]["summary"]["deleted_units"] == [
        "module@5(2)"
    ]
    assert stages["identity:outputs"]["added"] == 0
    assert stages["identity:calculations"]["summary"]["deleted_units"] == [
        "RandomFill@18"
    ]
    assert stages["identity:all"]["summary"]["deleted_units"] == [
        "Global Anchor@5"
    ]
    # the sly instruction passes the search's test and fails an audit,
    # which puts it back: identity keeps nothing unaudited
    search = stages["identity:calculations"]["summary"]["search"]
    assert search["rollbacks"] == 1
    assert search["status"] == "complete_singleton_certificate"
    # fitness takes the cheap module, output and calculations, then the
    # module's anchor; what the output fed is dead, to the strip after it
    added = [x["added"] for x in s["stages"]]
    assert added[9:16:2] == [3, 1, 2, 1]
    assert s["stages"][12]["summary"]["pruned"] == [17]
    assert stages["fitness:all"]["summary"]["deleted_units"] == [
        "Global Anchor@8"
    ]
    # the late cost passes the first confirmation, at the small size, and
    # not the second, at the full, which then bounds the search from above
    calculations = stages["fitness:calculations"]["summary"]
    assert calculations["retained_units"] == ["Terminal@1", "Local Anchor@19"]
    rounds = calculations["search"]["confirmations"]
    assert any(
        "reconfirm_replicates" in c and not c["accepted"] for c in rounds
    )
    every = [
        x["summary"]["search"]["reconfirm_every"] for x in s["stages"][9:16:2]
    ]
    # a full-size test that passes doubles the wait, from four, and one
    # that fails halves it, from stage to stage: the last two stages
    # each fail one and pass one
    assert every == [8, 16, 16, 16]
    final = stages["final"]["summary"]
    assert final["skeleton"]["n"] == 8 and final["wildtype"]["n"] == 20
    assert final["skeleton"]["mean"] == pytest.approx(0.5, abs=0.03)
    # each size's controls ran once, for every stage
    keys = [t["key"] for t in r["trials"]]
    for size, n in (("small", 40), ("screen", 20), ("full", 20)):
        controls = [k for k in keys if k.get("control") == size]
        assert sorted(k["replicate"] for k in controls) == list(range(n))
    assert all(
        ("control" in k) != ("stage" in k) and len(k) <= 3 for k in keys
    )
    # a screen is one competition on the screen's size of world, failed
    # under a share its controls would rarely fall below
    threshold = stages["fitness:modules"]["summary"]["screen_threshold"]
    shares = [
        t["result"]["score"]
        for t in r["trials"]
        if t["key"].get("control") == "screen"
    ]
    assert threshold == e2e_skeleton.lethal_share(shares, 0.001)
    assert 0.1 < threshold < min(shares)
    # a trial's weight is the seconds its competitions may take
    for t in r["trials"]:
        env, weight = t["request"]["env"], t["request"]["weight"]
        mode, cells = env["DISHTINY_MODE"], env.get("DISHTINY_N_CELLS")
        if mode in ("score", "screen"):
            limit = {"36": 60, "576": 600, "1024": 2400}[cells]
            assert weight == limit + 10
            assert env["DISHTINY_RUN_SECONDS"] == str(limit)
            assert "DISHTINY_WORLDS" not in env
            assert (mode == "screen") == ("DISHTINY_SCREEN_PASS" in env)
            if mode == "screen":
                assert float(env["DISHTINY_SCREEN_PASS"]) == threshold
        elif mode == "strip":
            assert weight == 1800
            assert env["DISHTINY_PRUNER_TIMEOUT"] == "1800"
            assert "DISHTINY_RUN_SECONDS" not in env
        else:
            assert mode == "identity"
            first = json.loads(env["DISHTINY_DIVERGENCE"])
            assert first == [[2048, 100, 56], [8192, 100, 222]]
            worlds = json.loads(env["DISHTINY_WORLDS"])
            if "fresh" not in t["key"]["key"]:
                assert worlds == [] and weight == 56 + 222
                continue
            assert [w[:2] for w in worlds[::5]] == [[12288, 36], [24576, 64]]
            assert [w[3] for w in worlds] == [60, 60, 60, 60, 213, 213]
            # each world's competition, and the wildtype's own
            assert weight == 56 + 222 + 2 * sum(w[3] + 10 for w in worlds)
    # a control is the wildtype, whatever the stage has knocked out
    for t in r["trials"]:
        if "control" in t["key"]:
            assert t["request"]["env"]["DISHTINY_KNOCKOUT"] == ""


def test_e2e_skeleton_skips_a_strip_whose_trial_fails():
    r = simulate_dispatch(
        "scd.assaylib.dishtiny_prq49.e2e_skeleton",
        {**KW, "stages": ["strip", "identity:all"]},
        fake_trial=lambda t: fake_trial(t, strip_fails=True),
        meta_seed=1,
        trial_maxretry=0,
    )
    assert r["completed"]["outcome"] == "succeeded", r["completed"]
    strip, identity = r["completed"]["summary"]["stages"]
    assert strip["added"] == 0 and "failed" in strip["summary"]["skipped"]
    # identity takes the dead code the strip did not, with the silent
    assert identity["added"] == 5


def test_e2e_skeleton_refuses_an_unknown_stage():
    r = simulate_dispatch(
        "scd.assaylib.dishtiny_prq49.e2e_skeleton",
        {**KW, "stages": ["polish"]},
        fake_trial=fake_trial,
        churn_maxretry=0,
    )
    assert r["completed"]["outcome"] == "failed"
    assert "unknown stage" in r["completed"]["reason"]


# -- the trial command, on stand-ins for rundishtiny and the pruner ----------

RUNDISHTINY = r'''#!/usr/bin/env python3
"""A stand-in for rundishtiny: an entrant's fitness is how many `Write Own
State` it has, and the census also shows every operation but the quiet."""
import csv, glob, hashlib, json, lzma, os, random, sys

import time

time.sleep(float(os.environ.get("STANDIN_SLEEP", "0")))
arg = dict(zip(sys.argv[1::2], sys.argv[2::2]))
quiet = {"Read Own State", "RandomFill", "Nop-0", "Nop-1", "Nop-2"}
programs = {}
for path in glob.glob("root_id=*"):
    ops = [x["operation"] for x in json.load(open(path))["value0"]["program"]]
    programs[int(path.split("=")[1].split("+")[0])] = ops
os.makedirs("outdata")
if arg.get("-TEST_INTERROOT_PHENOTYPE_DIFFERENTIATION") == "1":
    # the side-by-side test, of root ids 0 and 1, in place of a run: a
    # world of its own does not show a `Count Ones`
    assert arg["-RUN"] == "0" and int(arg["-PHENOTYPIC_DIVERGENCE_N_UPDATES"])
    shown = [[o for o in programs[r] if o not in quiet | {"Count Ones"}] for r in (0, 1)]
    with open("outdata/a=interroot_phenotype_differentiation+ext=.csv", "w") as fh:
        out = csv.writer(fh)
        out.writerow(["First Root ID", "Phenotype Divergence Detected"])
        out.writerow([0, int(shown[0] != shown[1])])
    sys.exit(0)
# a run ends after RUN_SECONDS, where it stands: here, 100 updates a second
updates, limit = int(arg["-RUN_UPDATES"]), int(arg["-RUN_SECONDS"])
updates = min(updates, 100 * limit) if limit else updates
fitness, loud = {}, []
for root_id in (1, 2):
    ops = programs[root_id]
    fitness[root_id] = ops.count("Write Own State")
    loud.append([o for o in ops if o not in quiet])
rng = random.Random(int(arg["-RNG_PRESEED"]))
share = fitness[1] / sum(fitness.values()) if sum(fitness.values()) else 0.5
owners = [1 if rng.random() < share else 2 for _ in range(int(arg["-N_CELLS"]))]
with open("outdata/a=coalescence_result+ext=.csv", "w") as fh:
    out = csv.writer(fh)
    out.writerow(["Root ID", "Count", "Update"])
    out.writerows([r, owners.count(r), updates] for r in (1, 2))
if arg.get("-CENSUS_WRITE") == "1":
    with lzma.open("outdata/a=cell_census+ext=.csv.xz", "wt") as fh:
        out = csv.writer(fh)
        out.writerow(["Metric", "Cell", "Update", "Value"])
        seen = hashlib.sha256(json.dumps(sorted(loud)).encode()).hexdigest()
        out.writerow(["seen", 0, updates, seen])
        out.writerows(["owner", i, 0, r] for i, r in enumerate(owners))
'''
PRUNER = r'''#!/usr/bin/env python3
"""A stand-in for sgpl-static: nops every `Subtract`."""
import json, sys

arg = dict(zip(sys.argv[1::2], sys.argv[2::2]))
assert arg["--solver"] == "stride711-split" and arg["--input-key"]
genome = json.load(open(arg["--input"]))
for x in genome["value0"]["program"]:
    if x["operation"] == "Subtract":
        x["operation"] = "Nop-0"
json.dump(genome, open(arg["--output"], "w"))
'''
PROGRAM = [
    "Global Anchor",
    "Write Own State",
    "Write Own State",
    "Read Own State",
    "RandomFill",
    "Add",
    "Subtract",
    "Nop-0",
    "Count Ones",
]


@pytest.fixture
def dishtiny(tmp_path, monkeypatch):
    for name, text in (("rundishtiny", RUNDISHTINY), ("pruner", PRUNER)):
        # by full path: compete shadows `python3` on rundishtiny's PATH
        text = text.replace("/usr/bin/env python3", sys.executable)
        (tmp_path / name).write_text(text)
        (tmp_path / name).chmod(0o755)
    genome = {
        "value0": {
            "program": [
                {"operation": o, "args": {}, "bitstring": "0"} for o in PROGRAM
            ]
        }
    }
    (tmp_path / "genome.json").write_text(json.dumps(genome))
    (tmp_path / "dishtiny.cfg").write_text("")
    for name in list(os.environ):
        if name.startswith("DISHTINY_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("DISHTINY_BINARY", str(tmp_path / "rundishtiny"))
    monkeypatch.setenv("DISHTINY_GENOME", str(tmp_path / "genome.json"))
    monkeypatch.setenv("DISHTINY_CONFIG", str(tmp_path / "dishtiny.cfg"))
    monkeypatch.setenv("DISHTINY_PRUNER", str(tmp_path / "pruner"))
    monkeypatch.setenv("DISHTINY_UPDATES", "64")
    monkeypatch.setenv("DISHTINY_N_CELLS", "100")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_compete_scores_the_candidates_share(dishtiny):
    neutral = compete({3}, 5, (64, 100))
    assert neutral["candidate_count"] + neutral["wildtype_count"] == 100
    assert neutral["score"] == pytest.approx(0.5, abs=0.2)
    assert "fingerprint" not in neutral and neutral["seed"] == 5
    assert compete({3}, 5, (64, 100)) == neutral  # a world is deterministic
    assert compete({3}, 6, (64, 100)) != neutral
    assert compete({1, 2}, 5, (64, 100))["score"] == 0.0
    halved = [compete({1}, s, (64, 400))["score"] for s in range(4)]
    assert all(0.2 < x < 0.45 for x in halved)  # a third, either root id
    # the census tells a quiet knockout from one that shows
    wildtype = compete(set(), 5, (64, 100), census=True)
    for knockout, same in (({3}, True), ({4}, True), ({5}, False)):
        got = compete(knockout, 5, (64, 100), census=True)
        assert (got["fingerprint"] == wildtype["fingerprint"]) == same


def test_a_competition_ends_where_it_stands_after_its_run_seconds(
    dishtiny, monkeypatch
):
    whole = compete({3}, 5, (640, 100))
    assert whole["updates"] == 640 and not whole["cut_short"]
    assert compete({3}, 5, (640, 100), run_seconds=7) == whole
    short = compete({3}, 5, (640, 100), run_seconds=2)
    assert short["updates"] == 200 and short["cut_short"]
    assert short["score"] == whole["score"]  # the stand-in's, either way
    # a run that ends early with one side gone was not cut short
    gone = compete({1, 2}, 5, (640, 100), run_seconds=2)
    assert gone["score"] == 0.0 and not gone["cut_short"]
    # a score is of the updates run; an identity world must run them
    # all, so one cut short shows nothing, and is not kept
    monkeypatch.setenv("DISHTINY_UPDATES", "640")
    monkeypatch.setenv("DISHTINY_RUN_SECONDS", "2")
    assert run_trial.run("score", {3}, None)["cut_short"]
    assert run_trial.run("identity", {3}, [[640, 100, 1, 7]])["accept"]
    monkeypatch.setenv("DISHTINY_CACHE", str(dishtiny / "cache"))
    unsure = run_trial.run("identity", {3}, [[640, 100, 1, 2]])
    assert not unsure["accept"] and "cut short" in unsure["inconclusive"]
    assert not list((dishtiny / "cache").rglob("*.json"))
    run_trial.fixed({3}, 1, (640, 100), census=True, run_seconds=7)
    assert len(list((dishtiny / "cache").rglob("*.json"))) == 1


def test_a_run_still_going_past_its_limit_is_killed_and_inconclusive(
    dishtiny, monkeypatch
):
    monkeypatch.setenv("STANDIN_SLEEP", "30")
    with pytest.raises(Inconclusive, match="killed after 0.3 seconds"):
        compete({3}, 5, (64, 100), kill_seconds=0.3)
    with pytest.raises(Inconclusive):
        diverges({3}, (64, 100), kill_seconds=0.3)
    # rundishtiny is to end by `run_seconds`, and is killed a little later
    monkeypatch.setenv("DISHTINY_RUN_SECONDS", "1")
    monkeypatch.setenv("DISHTINY_OVERHEAD_SECONDS", "0.3")
    monkeypatch.setenv("SCREENDOOR_TRIAL_DIR", "/x/a-trial-uuid")
    monkeypatch.setenv("DISHTINY_SCREEN_PASS", "0.1")
    # no score, no failed screen, and nothing accepted as identical
    scored = run_trial.run("score", {3}, None)
    assert scored["viable"] is False and "killed" in scored["inconclusive"]
    screened = run_trial.run("screen", {1, 2}, None)
    assert screened["accept"] and "inconclusive" in screened
    same = run_trial.run("identity", {3}, [[64, 100, 1, 1]])
    assert not same["accept"] and "inconclusive" in same
    monkeypatch.setenv("DISHTINY_DIVERGENCE", "[[64, 100, 0.3]]")
    assert "inconclusive" in run_trial.run("identity", {3}, [])


def test_identity_runs_the_side_by_side_test_first(dishtiny, monkeypatch):
    worlds = [[64, 100, 1], [64, 100, 2]]
    monkeypatch.setenv(
        "DISHTINY_DIVERGENCE", "[[64, 100, 30], [128, 100, 30]]"
    )
    assert diverges({5}, (64, 100)) and not diverges({3, 4}, (64, 100))
    # a knockout that shows side by side is rejected there
    assert run_trial.run("identity", {5}, worlds) == {
        "accept": False,
        "identical": 0,
        "diverged": 0,
    }
    # one that does not goes on to the competitions, if there are any:
    # a `Count Ones` shows only there
    assert not diverges({8}, (64, 100))
    assert run_trial.run("identity", {8}, []) == {
        "accept": True,
        "identical": 0,
    }
    assert run_trial.run("identity", {8}, worlds) == {
        "accept": False,
        "identical": 0,
    }
    assert run_trial.run("identity", {3, 4}, worlds) == {
        "accept": True,
        "identical": 2,
    }


def test_run_trial_modes(dishtiny, monkeypatch):
    worlds = [[64, 100, 1], [64, 100, 2], [128, 100, 3]]
    assert run_trial.run("identity", {3, 4}, worlds) == {
        "accept": True,
        "identical": 3,
    }
    assert run_trial.run("identity", {3, 5}, worlds) == {
        "accept": False,
        "identical": 0,
    }
    # a screen is one competition, failed at or under a share of cells
    monkeypatch.setenv("SCREENDOOR_TRIAL_DIR", "/x/a-trial-uuid")
    monkeypatch.setenv("DISHTINY_SCREEN_PASS", "0.1")
    passed = run_trial.run("screen", {3}, None)
    assert passed["accept"] and passed["score"] > 0.1
    monkeypatch.setenv("DISHTINY_SCREEN_PASS", str(passed["score"]))
    assert not run_trial.run("screen", {3}, None)["accept"]
    for least in ("0.1", "0.0", "-0.2"):  # extinct fails any threshold
        monkeypatch.setenv("DISHTINY_SCREEN_PASS", least)
        failed = run_trial.run("screen", {1, 2}, None)
        assert failed["score"] == 0.0 and not failed["accept"]
    assert run_trial.run("strip", {3}, None) == {"pruned": [6]}
    assert run_trial.run("strip", {6}, None) == {"pruned": []}
    with pytest.raises(ValueError):
        run_trial.run("bogus", set(), None)


def test_run_trial_recalls_fixed_worlds_and_sends_its_result(
    dishtiny, monkeypatch, capsys
):
    monkeypatch.setenv("DISHTINY_CACHE", str(dishtiny / "cache"))
    first = run_trial.fixed({3}, 1, (64, 100), census=True)
    assert len(list((dishtiny / "cache").rglob("*.json"))) == 1
    monkeypatch.setenv("DISHTINY_BINARY", "/nonexistent")  # recalled, not run
    assert run_trial.fixed({3}, 1, (64, 100), census=True) == first
    with pytest.raises(OSError):
        run_trial.fixed({3}, 2, (64, 100), census=True)
    monkeypatch.setenv("DISHTINY_BINARY", str(dishtiny / "rundishtiny"))
    monkeypatch.setenv("DISHTINY_MODE", "score")
    monkeypatch.setenv("DISHTINY_KNOCKOUT", "1-2")
    monkeypatch.setenv("SCREENDOOR_TRIAL_DIR", "/x/some-trial-uuid")
    assert run_trial.main() == 0
    marker, _, payload = capsys.readouterr().out.strip().partition(" ")
    assert marker == "!!!screendoor:payload"
    sent = json.loads(payload)
    assert sent["score"] == 0.0 and sent["cpu_s"] > 0
    assert run_trial.main() == 0  # the uuid seeds the world
    again = json.loads(capsys.readouterr().out.partition(" ")[2])
    assert again["seed"] == sent["seed"]


def test_lethal_share_fits_a_symmetric_beta_to_the_controls():
    rng = random.Random(0)
    controls = [rng.betavariate(7.0, 7.0) for _ in range(4000)]
    # the share a control falls under one time in a hundred, and a thousand
    for rate in (0.01, 0.001):
        threshold = e2e_skeleton.lethal_share(controls, rate)
        under = sum(x < threshold for x in controls) / len(controls)
        assert under == pytest.approx(rate, abs=3 * rate**0.5 / 4000**0.5)
    assert 0.0 < e2e_skeleton.lethal_share(controls, 1e-6) < threshold
    # tighter controls leave a higher threshold, and it is never negative
    tight = [0.5 + (x - 0.5) / 2 for x in controls]
    assert e2e_skeleton.lethal_share(tight, 0.001) > threshold
    wide = [rng.betavariate(0.5, 0.5) for _ in range(400)]
    assert 0.0 <= e2e_skeleton.lethal_share(wide, 0.001) < 0.01
    # controls that do not vary, or are all at the extremes, give none
    assert e2e_skeleton.lethal_share([0.5, 0.5], 0.001) == 0.0
    assert e2e_skeleton.lethal_share([0.0, 1.0], 0.001) == 0.0
