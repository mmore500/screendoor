import json
import os

import pytest

from screendoor import churn as scd_churn
from screendoor.auxlib._DispatchContext import load_dispatches
from screendoor.daemon import (
    kill_dispatch,
    print_status,
    resume_dispatch,
    run_tick_once,
    submit_dispatch,
)
from screendoor.testing import (
    INLINE_HOOKS,
    register_hook,
    simulate_dispatch,
    write_dispatchdir_hooks,
)

EXERCISE = "scd.assaylib.testing.exercise"


def submit(dispatchdir, assay, *, fake_trial=None, **settings):
    """Submit a dispatch on the inline orchestrator."""
    fake = register_hook(fake_trial)
    dispatch = {
        "assay": assay if isinstance(assay, str) else register_hook(assay),
        "schedule": "* * * * *",
        **INLINE_HOOKS,
        "how_launch": f"scd.orch.inline.launch(fake_trial={fake})",
        **settings,
    }
    return submit_dispatch(dispatch, dispatchdir)


def dispatch_events(dispatchdir, event):
    (ctx,) = load_dispatches(dispatchdir)
    events = [
        *ctx.ddhooks.read_dispatch_payloads(ctx.ddhooks),
        *ctx.ddhooks.read_dispatch_telemetry(ctx.ddhooks),
    ]
    return [e for e in events if e["event"] == event]


def test_submit_fills_uuid_and_seed(dispatchdir, clock):
    uid = submit_dispatch(
        {"assay": "x", "schedule": "*/5 * * * *", **INLINE_HOOKS}, dispatchdir
    )
    (ctx,) = load_dispatches(dispatchdir)
    assert ctx.dispatch_uuid == uid
    assert 0 <= ctx.record["meta_seed"] < 2**32
    assert ctx.labels["meta_seed"] == ctx.record["meta_seed"]
    assert ctx.record["trial_maxretry"] == 3


@pytest.mark.parametrize(
    "bad",
    [
        {"schedule": "* * * * *"},
        {"assay": "x"},
        {"assay": "x", "schedule": "* * *"},
        {
            "assay": "x",
            "schedule": "* * * * *",
            **INLINE_HOOKS,
            "how_nope": "1",
        },
        {"assay": "x", "schedule": "* * * * *", **INLINE_HOOKS, "typo_key": 1},
        {
            "assay": "x",
            "schedule": "* * * * *",
            **INLINE_HOOKS,
            "trial_batchsize": 0,
        },
    ],
)
def test_submit_rejects_bad(dispatchdir, bad):
    with pytest.raises(ValueError):
        submit_dispatch(bad, dispatchdir)


def test_schedule_due(dispatchdir, clock):
    submit(
        dispatchdir,
        EXERCISE,
        fake_trial=lambda t: True,
        assay_kwargs={"n": 1},
        schedule="*/5 * * * *",
    )
    run_tick_once(dispatchdir)  # the first tick comes at once
    assert len(dispatch_events(dispatchdir, "ticked")) == 1
    run_tick_once(dispatchdir)  # not yet due
    assert len(dispatch_events(dispatchdir, "ticked")) == 1
    clock.sleep(5 * 60)
    assert run_tick_once(dispatchdir) == []  # succeeded on the second tick
    assert len(dispatch_events(dispatchdir, "ticked")) == 2


def test_throttle_drops_launch_and_memo(dispatchdir, clock):
    r = simulate_dispatch(
        EXERCISE,
        {"n": 2},
        dispatchdir=dispatchdir,
        fake_trial=lambda t: 1,
        max_ticks=3,
        how_throttle_churn=register_hook(lambda ctx: False),
    )
    assert r["completed"] is None and r["trials"] == []


def test_relaunch_then_lost(dispatchdir, clock):
    def launch_nothing(ctx, name, batches):
        pass

    submit(
        dispatchdir,
        EXERCISE,
        assay_kwargs={"n": 1},
        trial_maxretry=2,
        how_launch=register_hook(launch_nothing),  # poke: every job vanished
    )
    for _ in range(6):
        run_tick_once(dispatchdir, force=True)
    (ctx,) = load_dispatches(dispatchdir)
    (t,) = ctx.read_trials()
    assert t["status"] == "failed" and t["error"]["kind"] == "lost"
    assert t["attempt"] == 2
    assert ctx.completed["outcome"] == "failed"


def test_kill_pauses_and_resume_relaunches_for_free(dispatchdir, clock):
    cancelled = []

    def launch_nothing(ctx, name, batches):
        pass

    uid = submit(
        dispatchdir,
        EXERCISE,
        assay_kwargs={"n": 1},
        trial_maxretry=0,
        how_launch=register_hook(launch_nothing),
        how_poke=register_hook(lambda ctx, trials: set()),  # all running
        how_kill=register_hook(lambda ctx, trials: cancelled.extend(trials)),
    )
    run_tick_once(dispatchdir)
    assert kill_dispatch(dispatchdir) == [uid]
    assert [(t["attempt"], t["job"]["index"]) for t in cancelled] == [(0, 0)]
    (ctx,) = load_dispatches(dispatchdir)
    (t,) = ctx.read_trials()
    assert ctx.killed and ctx.completed is None  # paused, not failed
    assert (t["status"], t["kills"]) == ("killed", 1)
    assert run_tick_once(dispatchdir, force=True) == []  # nothing active
    assert len(dispatch_events(dispatchdir, "ticked")) == 1
    (row,) = print_status(dispatchdir)
    assert row["state"] == "killed" and row["tally"]["kills"] == 1

    assert kill_dispatch(dispatchdir) == [uid]  # repeating is harmless
    assert len(cancelled) == 1
    assert resume_dispatch(dispatchdir) == [uid]
    run_tick_once(dispatchdir, force=True)
    (ctx,) = load_dispatches(dispatchdir)
    (t,) = ctx.read_trials()
    # relaunched although trial_maxretry is 0: a kill is not a retry
    assert (t["status"], t["attempt"]) == ("requested", 1)
    assert t["job"]["name"] != cancelled[0]["job"]["name"]  # a new job
    assert row["tally"]["retries"] == 0


def test_churn_errors_retry_then_fail(dispatchdir, clock):
    calls = []

    def churn(dispatch, trial_submissions, trial_payloads, memo):
        calls.append(1)
        raise RuntimeError("boom")

    submit(dispatchdir, churn, churn_maxretry=2)
    for _ in range(5):
        run_tick_once(dispatchdir, force=True)
    (ctx,) = load_dispatches(dispatchdir)
    assert len(calls) == 3  # the first failure, then 2 retries
    assert ctx.completed["outcome"] == "failed"
    assert len(dispatch_events(dispatchdir, "churn_error")) == 3
    notes = ctx.read_churn_notify()
    # one deduplicated churn error, then the completion
    assert sum(n["level"] == "failure" for n in notes) == 2


def test_churn_error_streak_resets(dispatchdir, clock):
    calls = []

    def churn(dispatch, trial_submissions, trial_payloads, memo):
        calls.append(1)
        if len(calls) in (1, 2, 4, 5):
            raise RuntimeError("flaky")
        return [scd_churn.succeed({})] if len(calls) >= 6 else []

    submit(dispatchdir, churn, churn_maxretry=2)
    for _ in range(7):
        run_tick_once(dispatchdir, force=True)
    (ctx,) = load_dispatches(dispatchdir)
    assert ctx.completed["outcome"] == "succeeded"


def test_duplicate_requests_dropped(clock, caplog):
    def churn(dispatch, trial_submissions, trial_payloads, memo):
        again = scd_churn.launch([{"key": 1, "cmd": "x"}])
        if trial_submissions:
            return [again, scd_churn.succeed({})]
        return [scd_churn.launch([{"key": 1, "cmd": "x"}] * 2)]

    r = simulate_dispatch(churn, fake_trial=lambda t: 0)
    assert len(r["trials"]) == 1
    assert caplog.text.count("duplicate") == 2


def test_memo_loop_same_tick(dispatchdir, clock):
    def churn(dispatch, trial_submissions, trial_payloads, memo):
        if len(memo) < 3:
            return [scd_churn.memo({"r": len(memo)})]
        return [scd_churn.succeed({"memos": len(memo)})]

    simulate_dispatch(churn, dispatchdir=dispatchdir, max_ticks=1)
    (ctx,) = load_dispatches(dispatchdir)
    assert ctx.completed["summary"] == {"memos": 3}
    memos = ctx.read_churn_memo_events()
    # each memo names the churn call that made it
    assert [m["churn_step"] for m in memos] == ["0:0", "1:0", "2:0"]


def test_trial_env(clock):
    cmd = (
        'echo "!!!screendoor:payload '
        '\\"${SCREENDOOR_SEED-unset} $i $(basename $SCREENDOOR_TRIAL_DIR)\\""'
    )
    r = simulate_dispatch(EXERCISE, {"n": 2, "cmd": cmd})
    for t in r["trials"]:
        seed, i, trial_dir = t["result"].split()
        assert seed == "unset"  # trials get no seed unless churn sends one
        assert int(i) == t["key"]["i"]
        assert trial_dir == t["trial_uuid"]


def test_every_record_carries_the_dispatch_labels(tmp_path, clock):
    r = simulate_dispatch(
        "scd.assaylib.skeletonization.jenga",
        {
            "components": list("abc"),
            "cmd": "echo '!!!screendoor:telemetry 1'\n"
            "echo '!!!screendoor:payload {\"accept\": false}'",
        },
        dispatchdir=str(tmp_path),
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
        "meta_redo": "0",
    }
    files = {p.name: p for p in tmp_path.rglob("*.jsonl")}
    assert set(files) == {
        "dispatch_submissions.jsonl",
        "dispatch_payloads.jsonl",
        "dispatch_telemetry.jsonl",
        "dispatch_notify.jsonl",  # the daemon's own, of no dispatch
        "trial_submissions.jsonl",
        "trial_payloads.jsonl",
        "churn_memo.jsonl",
        "churn_notify.jsonl",
        "trial_telemetry.jsonl",
    }
    del files["dispatch_notify.jsonl"]
    for path in files.values():
        for line in path.read_text().splitlines():
            record = json.loads(line)
            assert labels.items() <= record.items(), (path.name, record)
    (row,) = print_status(str(tmp_path))
    assert labels.items() <= row.items()


def test_submit_rejects_bad_names(dispatchdir):
    bad = {
        "assay": "x",
        "schedule": "* * * * *",
        **INLINE_HOOKS,
        "meta_project": 3,
    }
    with pytest.raises(ValueError, match="meta_project"):
        submit_dispatch(bad, dispatchdir)


def test_daemon_liveness_and_termination_hooks(tmp_path, clock):
    seen = []

    def notifier(ctx, level, message, data, history, now):
        seen.append((level, message))
        return [{"event": "sent"}]

    hook = register_hook(notifier)
    write_dispatchdir_hooks(
        str(tmp_path), how_notify_liveness=hook, how_notify_termination=hook
    )
    simulate_dispatch(
        EXERCISE, {"n": 1}, dispatchdir=str(tmp_path), clock=clock
    )
    levels = [level for level, _ in seen]
    assert set(levels[:-1]) == {"liveness"} and len(levels) >= 3
    assert seen[-1] == ("termination", "daemon exited: no active dispatches")
    records = (tmp_path / "dispatch_notify.jsonl").read_text().splitlines()
    assert len(records) == len(seen)


def test_status_shows_failures(dispatchdir, clock, capsys):
    simulate_dispatch(
        EXERCISE,
        {"n": 1, "cmd": "echo oops >&2; exit 3"},
        dispatchdir=dispatchdir,
    )
    (row,) = print_status(dispatchdir)
    (failure,) = row["failures"]
    assert (failure["kind"], failure["exit_code"]) == ("error", 3)
    assert "error, exit 3: oops" in capsys.readouterr().out


def test_status_and_setup_records(dispatchdir, clock, capsys):
    simulate_dispatch(EXERCISE, {"n": 2}, dispatchdir=dispatchdir)
    (row,) = print_status(dispatchdir)
    assert row["state"] == "succeeded"
    assert row["trials"] == {"succeeded": 2}
    assert row["tally"]["retries"] == 0 and row["failures"] == []
    assert "retries 0, kills 0" in capsys.readouterr().out
    (completed,) = dispatch_events(dispatchdir, "completed")
    assert completed["tally"] == row["tally"]
    (setup,) = dispatch_events(dispatchdir, "setup")
    launch = setup["hooks"]["how_launch"]
    assert launch["expr"].startswith("scd.orch.inline")
    assert "python_version" in setup
    assert json.loads(json.dumps(setup)) == setup


def test_every_hook_must_be_supplied(dispatchdir):
    from screendoor.auxlib._DispatchContext import MissingHookError

    partial = {k: v for k, v in INLINE_HOOKS.items() if k != "how_poke"}
    bad = {"assay": "x", "schedule": "* * * * *", **partial}
    del bad["how_cleanup_failure"]
    with pytest.raises(MissingHookError) as e:
        submit_dispatch(bad, dispatchdir)
    assert "how_poke" in str(e.value) and "how_cleanup_failure" in str(e.value)


def test_dispatchdir_hooks_must_be_supplied(tmp_path):
    from screendoor.auxlib._DispatchContext import (
        DispatchdirConfigError as MissingHookError,
    )

    ok = {"assay": "x", "schedule": "* * * * *", **INLINE_HOOKS}
    with pytest.raises(MissingHookError, match="screendoor.json is missing"):
        submit_dispatch(ok, str(tmp_path))
    path = write_dispatchdir_hooks(str(tmp_path))
    with open(path) as fh:
        config = json.load(fh)
    del config["how_log_info"]
    with open(path, "w") as fh:
        json.dump(config, fh)
    with pytest.raises(MissingHookError, match="must set how_log_info"):
        load_dispatches(str(tmp_path))


def test_run_dir_layout_and_redo(dispatchdir, clock):
    labels = {
        "meta_project": "proj",
        "meta_experiment": "exp",
        "meta_treatment": "a b",
        "meta_seed": 7,
    }
    r = simulate_dispatch(
        EXERCISE, {"n": 1}, dispatchdir=dispatchdir, clock=clock, **labels
    )
    (ctx,) = load_dispatches(dispatchdir)
    assert ctx.run_dir == os.path.join(
        dispatchdir, "project=proj", "date=2026-11-11+what=exp%a-b%7+redo=0"
    )
    stale = os.path.join(ctx.run_dir, "stale.txt")
    with open(stale, "w") as fh:
        fh.write("from the earlier dispatch")
    # same labels again: the run dir starts afresh
    simulate_dispatch(
        EXERCISE, {"n": 1}, dispatchdir=dispatchdir, clock=clock, **labels
    )
    assert not os.path.exists(stale)
    assert r["completed"]["outcome"] == "succeeded"


def test_submit_refuses_clashes(dispatchdir):
    base = {
        "assay": "x",
        "schedule": "* * * * *",
        "meta_seed": 1,
        **INLINE_HOOKS,
    }
    uid = submit_dispatch(base, dispatchdir)
    with pytest.raises(ValueError, match="change meta_redo"):
        submit_dispatch(base, dispatchdir)  # same labels, still open
    submit_dispatch({**base, "meta_redo": "1"}, dispatchdir)
    with pytest.raises(ValueError, match="already exists"):
        submit_dispatch(
            {**base, "meta_redo": "2", "dispatch_uuid": uid}, dispatchdir
        )
    with pytest.raises(ValueError, match="UUID"):
        submit_dispatch({**base, "dispatch_uuid": "nope"}, dispatchdir)


def test_dispatchdir_config_rejects_unknown_keys(tmp_path):
    from screendoor.auxlib._DispatchContext import DispatchdirConfigError

    write_dispatchdir_hooks(str(tmp_path), how_typo="logging.info")
    with pytest.raises(DispatchdirConfigError, match="unknown keys: how_typo"):
        load_dispatches(str(tmp_path))


def test_kill_and_resume_take_uuid_prefixes(dispatchdir, clock):
    uid = submit(dispatchdir, EXERCISE, assay_kwargs={"n": 1})
    assert kill_dispatch(dispatchdir, [uid[:8]]) == [uid]
    with pytest.raises(LookupError, match="matches 0"):
        resume_dispatch(dispatchdir, ["nope"])
    assert resume_dispatch(dispatchdir, [uid[:8]]) == [uid]
