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
from screendoor.orchestrate.subprocess._procs import is_alive


def _until_closed(workdir, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not run_tick_once(workdir, force=True):
            return load_dispatches(workdir)[0]
        time.sleep(0.2)
    raise AssertionError("dispatch never closed")


def test_subprocess_end_to_end(workdir):
    submit_dispatch(
        {
            "assay": "scd.assaylib.testing.exercise",
            "assay_kwargs": {
                "n": 5,
                "cmd": 'sleep 0.2; echo "!!!screendoor:result $i"',
            },
            "schedule": "* * * * *",
            "trial_batchsize": 2,
            "trial_batch_timeout": 30,
            "how_launch": "scd.orchestrate.subprocess.launch()",
            "how_poke": "scd.orchestrate.subprocess.poke()",
            "how_throttle": "scd.orchestrate.subprocess.throttle(max_procs=4)",
        },
        workdir,
    )
    ctx = _until_closed(workdir)
    assert ctx.closed["outcome"] == "succeeded"
    res = [o["result"] for o in ctx.closed["summary"]["outcomes"]]
    assert res == [0, 1, 2, 3, 4]
    jobs = {t["job_id"] for t in ctx.hook("how_read_payload")(ctx)}
    assert len(jobs) == 3  # 5 trials in batches of 2


def test_subprocess_timeout_relaunch_then_lost(workdir):
    submit_dispatch(
        {
            "assay": "scd.assaylib.testing.exercise",
            "assay_kwargs": {"n": 1, "cmd": "sleep 30"},
            "schedule": "* * * * *",
            "trial_batch_timeout": 1,
            "trial_maxretry": 1,
            "how_launch": "scd.orchestrate.subprocess.launch()",
            "how_poke": "scd.orchestrate.subprocess.poke()",
        },
        workdir,
    )
    ctx = _until_closed(workdir)
    (t,) = ctx.hook("how_read_payload")(ctx)
    assert t["status"] == "failed" and t["error"]["kind"] == "lost"
    assert t["attempt"] == 1


def test_adopt_after_crash_between_launch_and_record(workdir, monkeypatch):
    def die(ctx, entries, launch_id):
        ctx.hook("how_launch")(ctx, entries, launch_id)  # the job starts...
        raise KeyboardInterrupt  # ...and the daemon dies before recording it

    submit_dispatch(
        {
            "assay": "scd.assaylib.testing.exercise",
            "assay_kwargs": {"n": 2, "cmd": 'echo "!!!screendoor:result 1"'},
            "schedule": "* * * * *",
            "how_launch": "scd.orchestrate.subprocess.launch()",
            "how_poke": "scd.orchestrate.subprocess.poke()",
        },
        workdir,
    )
    with monkeypatch.context() as patch:
        patch.setattr(_apply_actions, "launch_entries", die)
        with pytest.raises(KeyboardInterrupt):
            run_tick_once(workdir, force=True)
    ctx = _until_closed(workdir)
    assert ctx.closed["outcome"] == "succeeded"
    trials = ctx.hook("how_read_payload")(ctx)
    assert all(t["attempt"] == 0 for t in trials)
    assert len(os.listdir(os.path.join(ctx.run_dir, "launches"))) == 1


def test_kill_stops_the_trial_processes(workdir):
    submit_dispatch(
        {
            "assay": "scd.assaylib.testing.exercise",
            "assay_kwargs": {"n": 1, "cmd": "echo $$ > pid; sleep 60"},
            "schedule": "* * * * *",
            "trial_batch_timeout": 120,
            "how_launch": "scd.orchestrate.subprocess.launch()",
            "how_poke": "scd.orchestrate.subprocess.poke()",
            "how_kill": "scd.orchestrate.subprocess.kill()",
        },
        workdir,
    )
    (ctx,) = run_tick_once(workdir)
    (t,) = ctx.hook("how_read_payload")(ctx)
    pidfile = os.path.join(ctx.trial_dir(t["trial_uuid"]), "pid")
    while not os.path.exists(pidfile):  # wait for the script to start
        time.sleep(0.05)
    with open(pidfile) as fh:
        script_pid = int(fh.read())
    kill_dispatch(workdir)
    deadline = time.time() + 10
    while os.path.exists(f"/proc/{script_pid}") and time.time() < deadline:
        time.sleep(0.05)
    assert not os.path.exists(f"/proc/{script_pid}")  # the script itself
    assert not is_alive(t["job_id"])
    (t,) = ctx.hook("how_read_payload")(ctx)
    assert (t["status"], t["kills"], t["error"]) == ("killed", 1, None)
    assert run_tick_once(workdir, force=True) == []
