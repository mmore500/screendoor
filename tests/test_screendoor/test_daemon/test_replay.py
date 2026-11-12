import io

from screendoor.auxlib import decode_sites
from screendoor.auxlib._DispatchContext import load_dispatches
from screendoor.daemon import replay_dispatch
from screendoor.testing import simulate_dispatch


def test_replay_matches(dispatchdir, clock):
    simulate_dispatch(
        "scd.assaylib.skeletonization.jenga",
        {"components": list("abcdef"), "cmd": "x", "batch_size": 3},
        fake_trial=lambda t: {"accept": "a" in t["env"]["components"]},
        dispatchdir=dispatchdir,
    )
    (ctx,) = load_dispatches(dispatchdir)
    out = io.StringIO()
    reports = replay_dispatch(ctx.run_dir, file=out)
    assert reports and all(r["match"] for r in reports), out.getvalue()


def test_replay_detects_changed_assay(dispatchdir, clock):
    simulate_dispatch(
        "scd.assaylib.skeletonization.hybrid",
        {"n_sites": 20, "cmd": "x", "batch_size": 8},
        fake_trial=lambda t: {
            "accept": {3, 4} <= decode_sites(t["env"]["retained"])
        },
        dispatchdir=dispatchdir,
    )
    (ctx,) = load_dispatches(dispatchdir)
    out = io.StringIO()
    assert all(r["match"] for r in replay_dispatch(ctx.run_dir, file=out))
    changed = replay_dispatch(
        ctx.run_dir, file=out, assay="scd.assaylib.skeletonization.ddmin"
    )
    assert not all(r["match"] for r in changed)
