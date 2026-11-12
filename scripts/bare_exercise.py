"""Run testing/exercise end to end with only screendoor installed."""

import json
import os
import subprocess
import sys
import tempfile
import time


def run(module: str, *args: str, **kwargs) -> str:
    argv = [sys.executable, "-m", f"screendoor.daemon.{module}", *args]
    proc = subprocess.run(
        argv, capture_output=True, text=True, check=True, **kwargs
    )
    return proc.stdout


dispatch = {
    "meta_project": "default",
    "meta_experiment": "default",
    "meta_treatment": "default",
    "meta_user": subprocess.check_output(["id", "-un"], text=True).strip(),
    "meta_redo": "0",
    "meta_seed": 1,
    "assay": "scd.churn.seed_global_rngs(scd.assaylib.testing.exercise)",
    "assay_kwargs": {"n": 4, "cmd": 'echo "!!!screendoor:payload $((i * i))"'},
    "schedule": "* * * * *",
    # every hook is spelled out: none has a default
    "how_launch": "scd.orch.subprocess.launch()",
    "how_poke": "scd.orch.subprocess.poke()",
    "how_kill": "scd.orch.subprocess.kill()",
    "how_throttle_churn": "scd.orch.subprocess.throttle(max_procs=4)",
    "how_setup": "scd.record.appendjsonl.setup()",
    "how_read_trial_submissions": "scd.record.appendjsonl.read_trial_submissions()",
    "how_write_trial_submissions": "scd.record.appendjsonl.write_trial_submissions()",
    "how_read_trial_payloads": "scd.record.appendjsonl.read_trial_payloads()",
    "how_write_trial_payloads": "scd.record.appendjsonl.write_trial_payloads()",
    "how_prep_trial_payloads": "scd.record.appendjsonl.prep_trial_payloads()",
    "how_read_trial_telemetry": "scd.record.appendjsonl.read_trial_telemetry()",
    "how_write_trial_telemetry": "scd.record.appendjsonl.write_trial_telemetry()",
    "how_read_churn_memo": "scd.record.appendjsonl.read_churn_memo()",
    "how_write_churn_memo": "scd.record.appendjsonl.write_churn_memo()",
    "how_read_churn_notify": "scd.record.appendjsonl.read_churn_notify()",
    "how_write_churn_notify": "scd.record.appendjsonl.write_churn_notify()",
    "how_notify_progress": "scd.notify.log.notify()",
    "how_notify_eta": "scd.notify.log.notify()",
    "how_notify_success": "scd.notify.log.notify()",
    "how_notify_failure": "scd.notify.log.notify()",
    "how_notify_warning": "scd.notify.log.notify()",
    "how_notify_anomaly": "scd.notify.log.notify()",
    "how_unblock_churn": "scd.unblock.all_trials_ready()",
    "how_cleanup_success": "scd.cleanup.tar(clear=True)",
    "how_cleanup_failure": "lambda ctx, completed: None",
}
# the daemon's own hooks
DISPATCHDIR_HOOKS = {
    "how_read_dispatch_submissions": "scd.record.appendjsonl.read_dispatch_submissions()",
    "how_write_dispatch_submissions": "scd.record.appendjsonl.write_dispatch_submissions()",
    "how_read_dispatch_payloads": "scd.record.appendjsonl.read_dispatch_payloads()",
    "how_write_dispatch_payloads": "scd.record.appendjsonl.write_dispatch_payloads()",
    "how_read_dispatch_telemetry": "scd.record.appendjsonl.read_dispatch_telemetry()",
    "how_write_dispatch_telemetry": "scd.record.appendjsonl.write_dispatch_telemetry()",
    "how_log_info": "logging.info",
    "how_notify_liveness": "scd.notify.null.notify()",
    "how_notify_termination": "scd.notify.log.notify()",
}
with tempfile.TemporaryDirectory() as dispatchdir:
    with open(os.path.join(dispatchdir, "screendoor.json"), "w") as fh:
        json.dump(DISPATCHDIR_HOOKS, fh, indent=2)
    run(
        "submit_dispatch",
        "-",
        "--dispatchdir",
        dispatchdir,
        input=json.dumps(dispatch),
    )
    for _ in range(100):
        run("run_tick_once", "--dispatchdir", dispatchdir, "--force")
        (row,) = json.loads(
            run("print_status", "--dispatchdir", dispatchdir, "--json")
        )
        if row["state"] != "open":
            break
        time.sleep(0.2)
assert row["state"] == "succeeded", row
results = [o["result"] for o in row["completed"]["summary"]["outcomes"]]
assert results == [0, 1, 4, 9], results
print("bare exercise ok")
