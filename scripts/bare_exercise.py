"""Run testing/exercise end to end with only screendoor installed."""

import json
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
    "meta_attempt": subprocess.check_output(["date"], text=True).strip(),
    "assay": "scd.assaylib.testing.exercise",
    "assay_kwargs": {"n": 4, "cmd": 'echo "!!!screendoor:result $((i * i))"'},
    "schedule": "* * * * *",
    "how_launch": "scd.orchestrate.subprocess.launch()",
    "how_poke": "scd.orchestrate.subprocess.poke()",
}
with tempfile.TemporaryDirectory() as workdir:
    run(
        "submit_dispatch",
        "-",
        "--workdir",
        workdir,
        input=json.dumps(dispatch),
    )
    for _ in range(100):
        run("run_tick_once", "--workdir", workdir, "--force")
        (row,) = json.loads(
            run("print_status", "--workdir", workdir, "--json")
        )
        if row["state"] != "open":
            break
        time.sleep(0.2)
assert row["state"] == "succeeded", row
results = [o["result"] for o in row["closed"]["summary"]["outcomes"]]
assert results == [0, 1, 4, 9], results
print("bare exercise ok")
