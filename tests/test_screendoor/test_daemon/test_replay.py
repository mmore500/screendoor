import io

from screendoor.assaylib.skeletonize._engine._codec import decode_sites
from screendoor.auxlib._DispatchContext import load_dispatches
from screendoor.daemon import replay_dispatch
from screendoor.testing import simulate_dispatch


def test_replay_matches(workdir, clock):
    simulate_dispatch(
        "scd.assaylib.skeletonize.naive_jenga",
        {"components": list("abcdef"), "cmd": "x", "width": 3},
        fake_trial=lambda t: {"passes": "a" in t["env"]["components"]},
        workdir=workdir,
    )
    (ctx,) = load_dispatches(workdir)
    out = io.StringIO()
    reports = replay_dispatch(ctx.run_dir, file=out)
    assert reports and all(r["match"] for r in reports), out.getvalue()


def test_replay_detects_changed_assay(workdir, clock):
    simulate_dispatch(
        "scd.assaylib.skeletonize.hybrid",
        {"n_sites": 20, "cmd": "x", "batch_size": 8},
        fake_trial=lambda t: {
            "accept": {3, 4} <= decode_sites(t["env"]["retained"])
        },
        workdir=workdir,
    )
    (ctx,) = load_dispatches(workdir)
    out = io.StringIO()
    assert all(r["match"] for r in replay_dispatch(ctx.run_dir, file=out))
    changed = replay_dispatch(
        ctx.run_dir, file=out, assay="scd.assaylib.skeletonize.ddmin"
    )
    assert not all(r["match"] for r in changed)
