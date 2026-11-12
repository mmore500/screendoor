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
from screendoor.orch.subprocess._procs import is_alive, pidfile
from screendoor.testing import INLINE_HOOKS


def _until_closed(workdir, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not run_tick_once(workdir, force=True):
            return load_dispatches(workdir)[0]
        time.sleep(0.2)
    raise AssertionError("dispatch never completed")


def test_subprocess_end_to_end(workdir):
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
        workdir,
    )
    ctx = _until_closed(workdir)
    assert ctx.completed["outcome"] == "succeeded"
    res = [o["result"] for o in ctx.completed["summary"]["outcomes"]]
    assert res == [0, 1, 2, 3, 4]
    jobs = {(t["job"]["name"], t["job"]["index"]) for t in ctx.read_trials()}
    assert len(jobs) == 3  # 5 trials in batches of 2


def test_subprocess_timeout_relaunch_then_lost(workdir):
    submit_dispatch(
        {
            "assay": "scd.assaylib.testing.exercise",
            "assay_kwargs": {"n": 1, "cmd": "sleep 30"},
            "schedule": "* * * * *",
            **INLINE_HOOKS,
            "trial_batch_timeout": 1,
            "trial_maxretry": 1,
            "how_launch": "scd.orch.subprocess.launch()",
            "how_poke": "scd.orch.subprocess.poke()",
        },
        workdir,
    )
    ctx = _until_closed(workdir)
    (t,) = ctx.read_trials()
    assert t["status"] == "failed" and t["error"]["kind"] == "lost"
    assert t["attempt"] == 1


def test_running_jobs_survive_a_daemon_crash(workdir, monkeypatch):
    real = _apply_actions.submit_trials

    def die(ctx, entries):
        real(ctx, entries)  # the jobs start...
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
        workdir,
    )
    with monkeypatch.context() as patch:
        patch.setattr(_apply_actions, "submit_trials", die)
        with pytest.raises(KeyboardInterrupt):
            run_tick_once(workdir, force=True)
    ctx = _until_closed(workdir)
    assert ctx.completed["outcome"] == "succeeded"
    trials = ctx.read_trials()
    assert all(t["attempt"] == 0 for t in trials)  # poke found them alive
    assert len(os.listdir(os.path.join(ctx.run_dir, "jobs"))) == 1


def test_kill_stops_the_trial_processes(workdir):
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
        workdir,
    )
    (ctx,) = run_tick_once(workdir)
    (t,) = ctx.read_trials()
    script_pidfile = os.path.join(ctx.trial_dir(t["trial_uuid"]), "pid")
    while not os.path.exists(script_pidfile):  # wait for the script
        time.sleep(0.05)
    with open(script_pidfile) as fh:
        script_pid = int(fh.read())
    kill_dispatch(workdir)
    deadline = time.time() + 10
    while os.path.exists(f"/proc/{script_pid}") and time.time() < deadline:
        time.sleep(0.05)
    assert not os.path.exists(f"/proc/{script_pid}")  # the script itself
    assert not is_alive(pidfile(ctx, t["job"]))
    (t,) = ctx.read_trials()
    assert (t["status"], t["kills"], t["error"]) == ("killed", 1, None)
    assert run_tick_once(workdir, force=True) == []
