"""Crash after every append in turn; resuming must reach the same result
with no (trial, attempt) submitted twice."""

import collections

import pytest

from screendoor.assaylib.skeletonization._engine._codec import decode_sites
from screendoor.auxlib._DispatchContext import load_dispatches
from screendoor.testing import (
    FakeClock,
    InjectedCrash,
    inject_crash_points,
    simulate_dispatch,
)

ASSAYS = [
    (
        "scd.assaylib.skeletonization.hybrid",
        {"n_sites": 12, "cmd": "x", "batch_size": 4},
        lambda t: {
            "accept": {1, 5, 6, 11} <= decode_sites(t["env"]["retained"])
        },
    ),
    (
        "scd.assaylib.skeletonization.naive_jenga",
        {"components": list("abcde"), "cmd": "x", "width": 2},
        lambda t: {"passes": "c" in t["env"]["components"].split()},
    ),
]


def max_repeats(workdir):
    """The most times any (trial, attempt) was submitted."""
    (ctx,) = load_dispatches(workdir)
    counts = collections.Counter(
        (e["trial_uuid"], e["attempt"])
        for e in ctx.read_trial_submissions()
        if e["event"] == "requested"
    )
    return max(counts.values())


@pytest.mark.parametrize("assay,kwargs,fake_trial", ASSAYS)
def test_crash_everywhere(tmp_path, assay, kwargs, fake_trial):
    def simulate(workdir, clock, **settings):
        return simulate_dispatch(
            assay,
            kwargs,
            fake_trial=fake_trial,
            workdir=workdir,
            clock=clock,
            **settings,
        )

    with FakeClock() as clock:
        want = simulate(str(tmp_path / "clean"), clock)["completed"]["summary"]
    n_appends = sum(
        len(p.read_text().splitlines())
        for p in (tmp_path / "clean").rglob("*.jsonl")
    )
    assert n_appends > 20
    for crash_at in range(1, n_appends + 1):
        workdir = str(tmp_path / f"crash{crash_at}")
        with FakeClock() as clock:
            try:
                with inject_crash_points(crash_at):
                    simulate(workdir, clock)
            except InjectedCrash:
                pass
            # resume; or, if the crash came while submitting, submit again
            r = simulate(workdir, clock, submit=not load_dispatches(workdir))
        assert r["completed"] is not None, crash_at
        got = r["completed"]["summary"]
        for k in ("retained", "skeleton", "certified"):
            assert got.get(k) == want.get(k), (crash_at, k)
        assert max_repeats(workdir) == 1, crash_at
