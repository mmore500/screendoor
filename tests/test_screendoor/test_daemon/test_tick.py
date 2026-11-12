import json

import pytest

from screendoor import act
from screendoor.auxlib._DispatchContext import load_dispatches
from screendoor.daemon import (
    kill_dispatch,
    print_status,
    resume_dispatch,
    run_tick_once,
    submit_dispatch,
)
from screendoor.rng import trial_seed
from screendoor.testing import register_hook, simulate_dispatch

EXERCISE = "scd.assaylib.testing.exercise"


def submit(workdir, assay, *, fake_trial=None, **settings):
    """Submit a dispatch on the inline orchestrator."""
    fake = register_hook(fake_trial)
    dispatch = {
        "assay": assay if isinstance(assay, str) else register_hook(assay),
        "schedule": "* * * * *",
        "how_launch": f"scd.orchestrate.inline.launch(fake_trial={fake})",
        "how_poke": "scd.orchestrate.inline.poke()",
        **settings,
    }
    return submit_dispatch(dispatch, workdir)


def dispatch_events(workdir, event):
    (ctx,) = load_dispatches(workdir)
    events = ctx.wdhooks.read_dispatch(workdir)
    return [e for e in events if e["event"] == event]


def test_submit_fills_uuid_and_seed(workdir, clock):
    uid = submit_dispatch({"assay": "x", "schedule": "*/5 * * * *"}, workdir)
    (ctx,) = load_dispatches(workdir)
    assert ctx.dispatch_uuid == uid
    assert isinstance(ctx.record["seed"], int)
    assert ctx.record["trial_maxretry"] == 3


@pytest.mark.parametrize(
    "bad",
    [
        {"schedule": "* * * * *"},
        {"assay": "x"},
        {"assay": "x", "schedule": "* * *"},
        {"assay": "x", "schedule": "* * * * *", "how_nope": "1"},
        {"assay": "x", "schedule": "* * * * *", "typo_key": 1},
        {"assay": "x", "schedule": "* * * * *", "trial_batchsize": 0},
    ],
)
def test_submit_rejects_bad(workdir, bad):
    with pytest.raises(ValueError):
        submit_dispatch(bad, workdir)


def test_schedule_due(workdir, clock):
    submit(
        workdir,
        EXERCISE,
        fake_trial=lambda t: True,
        assay_kwargs={"n": 1},
        schedule="*/5 * * * *",
    )
    run_tick_once(workdir)  # the first tick comes at once
    assert len(dispatch_events(workdir, "ticked")) == 1
    run_tick_once(workdir)  # not yet due
    assert len(dispatch_events(workdir, "ticked")) == 1
    clock.sleep(5 * 60)
    assert run_tick_once(workdir) == []  # succeeded on the second tick
    assert len(dispatch_events(workdir, "ticked")) == 2


def test_throttle_drops_launch_and_memo(workdir, clock):
    r = simulate_dispatch(
        EXERCISE,
        {"n": 2},
        workdir=workdir,
        fake_trial=lambda t: 1,
        max_ticks=3,
        how_throttle=register_hook(lambda ctx: False),
    )
    assert r["closed"] is None and r["trials"] == []


def test_relaunch_then_lost(workdir, clock):
    def launch_nothing(ctx, entries, launch_id):
        return [{**e, "job_id": "j"} for e in entries]

    submit(
        workdir,
        EXERCISE,
        assay_kwargs={"n": 1},
        trial_maxretry=2,
        how_launch=register_hook(launch_nothing),  # poke: every job vanished
    )
    for _ in range(6):
        run_tick_once(workdir, force=True)
    (ctx,) = load_dispatches(workdir)
    (t,) = ctx.hook("how_read_payload")(ctx)
    assert t["status"] == "failed" and t["error"]["kind"] == "lost"
    assert t["attempt"] == 2
    assert ctx.closed["outcome"] == "failed"


def test_kill_pauses_and_resume_relaunches_for_free(workdir, clock):
    cancelled = []

    def launch_nothing(ctx, entries, launch_id):
        return [{**e, "job_id": f"j{e['attempt']}"} for e in entries]

    uid = submit(
        workdir,
        EXERCISE,
        assay_kwargs={"n": 1},
        trial_maxretry=0,
        how_launch=register_hook(launch_nothing),
        how_poke=register_hook(lambda ctx, launched: set()),
        how_kill=register_hook(lambda ctx, trials: cancelled.extend(trials)),
    )
    run_tick_once(workdir)
    assert kill_dispatch(workdir) == [uid]
    assert [t["job_id"] for t in cancelled] == ["j0"]
    (ctx,) = load_dispatches(workdir)
    (t,) = ctx.hook("how_read_payload")(ctx)
    assert ctx.killed and ctx.closed is None  # paused, not failed
    assert (t["status"], t["kills"]) == ("killed", 1)
    assert run_tick_once(workdir, force=True) == []  # nothing active
    assert len(dispatch_events(workdir, "ticked")) == 1
    (row,) = print_status(workdir)
    assert row["state"] == "killed" and row["tally"]["kills"] == 1

    assert kill_dispatch(workdir) == [uid]  # repeating is harmless
    assert len(cancelled) == 1
    assert resume_dispatch(workdir) == [uid]
    run_tick_once(workdir, force=True)
    (ctx,) = load_dispatches(workdir)
    (t,) = ctx.hook("how_read_payload")(ctx)
    # relaunched although trial_maxretry is 0: a kill is not a retry
    assert (t["status"], t["attempt"], t["job_id"]) == ("launched", 1, "j1")
    assert row["tally"]["retries"] == 0


def test_churn_errors_retry_then_fail(workdir, clock):
    calls = []

    def churn(dispatch, trials, memo, *, rng):
        calls.append(1)
        raise RuntimeError("boom")

    submit(workdir, churn, churn_maxretry=2)
    for _ in range(5):
        run_tick_once(workdir, force=True)
    (ctx,) = load_dispatches(workdir)
    assert len(calls) == 3  # the first failure, then 2 retries
    assert ctx.closed["outcome"] == "failed"
    assert len(dispatch_events(workdir, "churn_error")) == 3
    notes = ctx.hook("how_read_notify")(ctx)
    # one deduplicated churn error, then the close
    assert sum(n["level"] == "failure" for n in notes) == 2


def test_churn_error_streak_resets(workdir, clock):
    calls = []

    def churn(dispatch, trials, memo, *, rng):
        calls.append(1)
        if len(calls) in (1, 2, 4, 5):
            raise RuntimeError("flaky")
        return [act.succeed({})] if len(calls) >= 6 else []

    submit(workdir, churn, churn_maxretry=2)
    for _ in range(7):
        run_tick_once(workdir, force=True)
    (ctx,) = load_dispatches(workdir)
    assert ctx.closed["outcome"] == "succeeded"


def test_duplicate_requests_dropped(clock, caplog):
    def churn(dispatch, trials, memo, *, rng):
        again = act.launch([{"key": 1, "cmd": "x"}])
        if trials:
            return [again, act.succeed({})]
        return [act.launch([{"key": 1, "cmd": "x"}] * 2)]

    r = simulate_dispatch(churn, fake_trial=lambda t: 0)
    assert len(r["trials"]) == 1
    assert caplog.text.count("duplicate") == 2


def test_memo_loop_same_tick(workdir, clock):
    def churn(dispatch, trials, memo, *, rng):
        if len(memo) < 3:
            return [act.memo({"r": len(memo)})]
        return [act.succeed({"memos": len(memo)})]

    simulate_dispatch(churn, workdir=workdir, max_ticks=1)
    (ctx,) = load_dispatches(workdir)
    assert ctx.closed["summary"] == {"memos": 3}
    memos = ctx.hook("how_read_memo")(ctx, raw=True)
    # every step had its own random stream
    assert len({m["step_seed"] for m in memos}) == 3


def test_trial_seed_and_env(clock):
    cmd = (
        'echo "!!!screendoor:result '
        '\\"$SCREENDOOR_SEED $i $(basename $SCREENDOOR_TRIAL_DIR)\\""'
    )
    r = simulate_dispatch(EXERCISE, {"n": 2, "cmd": cmd})
    (ctx,) = load_dispatches(r["workdir"])
    for t in r["trials"]:
        seed, i, trial_dir = t["result"].split()
        assert int(seed) == trial_seed(ctx.seed, t["trial_uuid"])
        assert int(i) == t["key"]["i"]
        assert trial_dir == t["trial_uuid"]


def test_every_record_carries_the_dispatch_labels(tmp_path, clock):
    r = simulate_dispatch(
        "scd.assaylib.skeletonize.naive_jenga",
        {
            "components": list("abc"),
            "cmd": "echo '!!!screendoor:telemetry 1'\n"
            "echo '!!!screendoor:result {\"passes\": false}'",
        },
        workdir=str(tmp_path),
        clock=clock,
        how_notify_progress="scd.notify.log.notify()",
        meta_experiment="exp1",
    )
    labels = {
        "dispatch_uuid": r["dispatch_uuid"],
        "meta_project": "default",
        "meta_experiment": "exp1",
        "meta_treatment": "default",
        "meta_user": "default",
        "meta_attempt": "default",
    }
    files = {p.name: p for p in tmp_path.rglob("*.jsonl")}
    assert set(files) == {
        "screendoor-dispatch.jsonl",
        "screendoor-notify.jsonl",  # the daemon's own, of no dispatch
        "payload.jsonl",
        "memo.jsonl",
        "notify.jsonl",
        "telemetry.jsonl",
    }
    del files["screendoor-notify.jsonl"]
    for path in files.values():
        for line in path.read_text().splitlines():
            record = json.loads(line)
            assert labels.items() <= record.items(), (path.name, record)
    (row,) = print_status(str(tmp_path))
    assert labels.items() <= row.items()


def test_submit_rejects_bad_names(workdir):
    bad = {"assay": "x", "schedule": "* * * * *", "meta_project": 3}
    with pytest.raises(ValueError, match="meta_project"):
        submit_dispatch(bad, workdir)


def test_daemon_liveness_and_termination_hooks(tmp_path, clock):
    seen = []

    def notifier(ctx, level, message, data, history, now):
        seen.append((level, message))
        return [{"event": "sent"}]

    hook = register_hook(notifier)
    config = {"how_notify_liveness": hook, "how_notify_termination": hook}
    (tmp_path / "screendoor.json").write_text(json.dumps(config))
    simulate_dispatch(EXERCISE, {"n": 1}, workdir=str(tmp_path), clock=clock)
    levels = [level for level, _ in seen]
    assert set(levels[:-1]) == {"liveness"} and len(levels) >= 3
    assert seen[-1] == ("termination", "daemon exited: no active dispatches")
    records = (tmp_path / "screendoor-notify.jsonl").read_text().splitlines()
    assert len(records) == len(seen)


def test_status_shows_failures(workdir, clock, capsys):
    simulate_dispatch(
        EXERCISE, {"n": 1, "cmd": "echo oops >&2; exit 3"}, workdir=workdir
    )
    (row,) = print_status(workdir)
    (failure,) = row["failures"]
    assert (failure["kind"], failure["exit_code"]) == ("error", 3)
    assert "error, exit 3: oops" in capsys.readouterr().out


def test_status_and_setup_records(workdir, clock, capsys):
    simulate_dispatch(EXERCISE, {"n": 2}, workdir=workdir)
    (row,) = print_status(workdir)
    assert row["state"] == "succeeded"
    assert row["trials"] == {"succeeded": 2}
    assert row["tally"]["retries"] == 0 and row["failures"] == []
    assert "retries 0, kills 0" in capsys.readouterr().out
    (closed,) = dispatch_events(workdir, "closed")
    assert closed["tally"] == row["tally"]
    (setup,) = dispatch_events(workdir, "setup")
    launch = setup["hooks"]["how_launch"]
    assert launch["expr"].startswith("scd.orchestrate.inline")
    assert "python_version" in setup
    assert json.loads(json.dumps(setup)) == setup
