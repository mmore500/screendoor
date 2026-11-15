import os
import time

import pytest

from screendoor.auxlib._DispatchContext import load_dispatches
from screendoor.daemon import (
    _apply_actions,
    kill_dispatch,
    run_tick_once,
    submit_dispatch,
)
from screendoor.orch.subprocess import throttle
from screendoor.orch.subprocess._procs import is_alive, pidfile
from screendoor.testing import INLINE_HOOKS


def _until_closed(dispatchdir, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not run_tick_once(dispatchdir, force=True):
            return load_dispatches(dispatchdir)[0]
        time.sleep(0.2)
    raise AssertionError("dispatch never completed")


def _wait_until(condition, timeout=30):
    """Poll until `condition()` holds, and return whether it came to."""
    deadline = time.time() + timeout
    while not condition() and time.time() < deadline:
        time.sleep(0.05)
    return condition()


def test_subprocess_end_to_end(dispatchdir):
    submit_dispatch(
        {
            "assay": "scd.assaylib.testing.exercise",
            "assay_kwargs": {
                "n": 5,
                "cmd": 'sleep 0.2; echo "!!!screendoor:payload $i"',
            },
            "schedule": "* * * * *",
            **INLINE_HOOKS,
            "trial_batchsize": 2,
            "trial_batch_timeout": 30,
            "how_launch": "scd.orch.subprocess.launch()",
            "how_poke": "scd.orch.subprocess.poke()",
            "how_throttle_churn": "scd.orch.subprocess.throttle(max_procs=4)",
        },
        dispatchdir,
    )
    ctx = _until_closed(dispatchdir)
    assert ctx.completed["outcome"] == "succeeded"
    res = [o["result"] for o in ctx.completed["summary"]["outcomes"]]
    assert res == [0, 1, 2, 3, 4]
    jobs = {(t["job"]["name"], t["job"]["index"]) for t in ctx.read_trials()}
    assert len(jobs) == 3  # 5 trials in batches of 2


def test_subprocess_timeout_relaunch_then_lost(dispatchdir):
    submit_dispatch(
        {
            "assay": "scd.assaylib.testing.exercise",
            "assay_kwargs": {"n": 1, "cmd": "sleep 30"},
            "schedule": "* * * * *",
            **INLINE_HOOKS,
            "trial_batch_timeout": 1,
            "trial_maxretry": 1,
            "churn_maxretry": 0,
            "how_launch": "scd.orch.subprocess.launch()",
            "how_poke": "scd.orch.subprocess.poke()",
        },
        dispatchdir,
    )
    ctx = _until_closed(dispatchdir)
    (t,) = ctx.read_trials()
    assert (t["status"], t["exit_code"], t["attempt"]) == ("failed", None, 1)


def test_running_jobs_survive_a_daemon_crash(dispatchdir, monkeypatch):
    real = _apply_actions.submit_trials

    def die(ctx, entries, n_trials):
        real(ctx, entries, n_trials)  # the jobs start...
        raise KeyboardInterrupt  # ...and the daemon dies mid-tick

    submit_dispatch(
        {
            "assay": "scd.assaylib.testing.exercise",
            "assay_kwargs": {"n": 2, "cmd": 'echo "!!!screendoor:payload 1"'},
            "schedule": "* * * * *",
            **INLINE_HOOKS,
            "how_launch": "scd.orch.subprocess.launch()",
            "how_poke": "scd.orch.subprocess.poke()",
        },
        dispatchdir,
    )
    with monkeypatch.context() as patch:
        patch.setattr(_apply_actions, "submit_trials", die)
        with pytest.raises(KeyboardInterrupt):
            run_tick_once(dispatchdir, force=True)
    ctx = _until_closed(dispatchdir)
    assert ctx.completed["outcome"] == "succeeded"
    trials = ctx.read_trials()
    assert all(t["attempt"] == 0 for t in trials)  # poke found them alive
    assert len(os.listdir(os.path.join(ctx.run_dir, "jobs"))) == 1


def test_throttle_counts_running_batches(dispatchdir):
    submit_dispatch(
        {
            "assay": "scd.assaylib.testing.exercise",
            "assay_kwargs": {"n": 2, "cmd": "sleep 60"},
            "schedule": "* * * * *",
            **INLINE_HOOKS,
            "trial_batch_timeout": 120,
            "how_launch": "scd.orch.subprocess.launch()",
            "how_poke": "scd.orch.subprocess.poke()",
            "how_kill": "scd.orch.subprocess.kill()",
        },
        dispatchdir,
    )
    (ctx,) = run_tick_once(dispatchdir)  # two batches, now running
    assert not throttle(max_procs=2)(ctx.hook_ctx)
    assert throttle(max_procs=3)(ctx.hook_ctx)
    kill_dispatch(dispatchdir)
    assert _wait_until(lambda: throttle(max_procs=1)(ctx.hook_ctx))


def test_kill_stops_the_trial_processes(dispatchdir):
    submit_dispatch(
        {
            "assay": "scd.assaylib.testing.exercise",
            "assay_kwargs": {
                "n": 1,
                "cmd": 'echo $$ > "$SCREENDOOR_TRIAL_DIR/pid"; sleep 60',
            },
            "schedule": "* * * * *",
            **INLINE_HOOKS,
            "trial_batch_timeout": 120,
            "how_launch": "scd.orch.subprocess.launch()",
            "how_poke": "scd.orch.subprocess.poke()",
            "how_kill": "scd.orch.subprocess.kill()",
        },
        dispatchdir,
    )
    (ctx,) = run_tick_once(dispatchdir)
    (t,) = ctx.read_trials()
    script_pidfile = os.path.join(ctx.trial_dir(t["trial_uuid"]), "pid")

    def script_pid():  # None until the script has written it whole
        try:
            with open(script_pidfile) as fh:
                text = fh.read()
        except FileNotFoundError:
            return None
        return int(text) if text.endswith("\n") else None

    assert _wait_until(lambda: script_pid() is not None)
    script = f"/proc/{script_pid()}"
    kill_dispatch(dispatchdir)
    # the script itself, and the batch around it, which ends after it
    assert _wait_until(lambda: not os.path.exists(script))
    assert _wait_until(lambda: not is_alive(pidfile(ctx.hook_ctx, t["job"])))
    (t,) = ctx.read_trials()
    assert (t["status"], t["kills"], t["result"]) == ("killed", 1, None)
    assert run_tick_once(dispatchdir, force=True) == []
