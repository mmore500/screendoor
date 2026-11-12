import os
import tarfile

from screendoor.auxlib._DispatchContext import load_dispatches
from screendoor.testing import simulate_dispatch

KEEP = "lambda *args, **kwargs: None"  # keep trials/ to look at


def run(cmd, **settings):
    """Run ``cmd`` as one real trial; return the trial and its context."""
    r = simulate_dispatch(
        "scd.assaylib.testing.exercise",
        {"n": 1, "cmd": cmd},
        **{
            "how_cleanup_success": KEEP,
            "how_cleanup_failure": KEEP,
            **settings,
        },
    )
    (ctx,) = load_dispatches(r["workdir"])
    return r["trials"][0], ctx


def test_tags_and_channels():
    t, ctx = run(
        "echo '!!!screendoor:telemetry {\"e\": 1}'\n"
        "echo '!!!screendoor:telemetry {\"e\": 2}' >&2\n"
        "echo '!!!screendoor:custom [1,2]'\n"
        "echo '!!!screendoor:payload 1'\n"
        "echo '!!!screendoor:payload {\"final\": true}'\n"
    )
    assert t["status"] == "succeeded"
    assert t["result"] == {"final": True}  # last one wins
    assert sorted(x["e"] for x in t["channels"]["telemetry"]) == [1, 2]
    assert t["channels"]["custom"] == [[1, 2]]
    events = ctx.hook("how_read_trial_telemetry")(ctx)
    assert sorted(e["event"] for e in events) == [
        "started",  # the worker's: when and where the trial ran
        "telemetry",
        "telemetry",
    ]
    (started,) = [e for e in events if e["event"] == "started"]
    assert started["host"] and started["pid"]
    payloads = ctx.read_trial_payloads()
    assert [e["event"] for e in payloads] == ["completed"]


def test_malformed_lines_go_to_telemetry():
    t, ctx = run(
        "echo '!!!screendoor:telemetry {nope'\n"
        "echo '!!!screendoor:payload {nope'\n"
        "echo '!!!screendoor:payload 7'\n"
    )
    assert (t["status"], t["result"], t["malformed"]) == ("succeeded", 7, 2)
    events = [
        e
        for e in ctx.hook("how_read_trial_telemetry")(ctx)
        if e["event"] != "started"
    ]
    assert [e["event"] for e in events] == ["malformed", "malformed"]
    assert [e["channel"] for e in events] == ["telemetry", "payload"]


def test_no_result_is_null():
    for cmd in ("echo hi", "echo '!!!screendoor:payload {nope'"):
        t, _ = run(cmd)
        assert (t["status"], t["result"], t["error"]) == (
            "succeeded",
            None,
            None,
        )


def test_error_kinds():
    t, _ = run("echo oops >&2; exit 3")
    assert t["status"] == "failed"
    assert t["error"]["kind"] == "error" and t["error"]["exit_code"] == 3
    assert "oops" in t["error"]["stderr_tail"]
    t, _ = run("echo '!!!screendoor:payload 1'; false")
    assert t["error"]["kind"] == "error"


def test_trial_dir_layout():
    t, ctx = run("echo '!!!screendoor:payload 1'; echo out; echo err >&2")

    def read(*parts):
        with open(os.path.join(ctx.trial_dir(t["trial_uuid"]), *parts)) as fh:
            return fh.read()

    assert read("cmd.sh").startswith("echo")
    assert "out" in read("attempt-0", "stdout.txt")
    assert "err" in read("attempt-0", "stderr.txt")


def test_script_runs_in_a_temporary_directory():
    t, ctx = run(
        'pwd > "$SCREENDOOR_TRIAL_DIR/cwd"; touch scratch-file; '
        "echo '!!!screendoor:payload 1'"
    )
    trial_dir = ctx.trial_dir(t["trial_uuid"])
    with open(os.path.join(trial_dir, "cwd")) as fh:
        cwd = fh.read().strip()
    assert not cwd.startswith(trial_dir)
    assert not os.path.exists(cwd)  # deleted after the trial
    assert not os.path.exists(os.path.join(trial_dir, "scratch-file"))


def test_success_archives_then_clears_trials(tmp_path):
    r = simulate_dispatch(
        "scd.assaylib.testing.exercise",
        {"n": 2, "cmd": "echo out; echo '!!!screendoor:payload 1'"},
        workdir=str(tmp_path),
    )
    assert r["completed"]["outcome"] == "succeeded"
    (ctx,) = load_dispatches(r["workdir"])
    assert not os.path.exists(os.path.join(ctx.run_dir, "trials"))
    with tarfile.open(os.path.join(ctx.run_dir, "trials.tar.gz")) as archive:
        names = archive.getnames()
    for t in r["trials"]:
        assert f"trials/{t['trial_uuid']}/attempt-0/stdout.txt" in names


def test_failure_keeps_trials_by_default(tmp_path):
    r = simulate_dispatch(
        "scd.assaylib.testing.exercise",
        {"n": 1, "cmd": "exit 1"},
        workdir=str(tmp_path),
    )
    assert r["completed"]["outcome"] == "failed"
    (ctx,) = load_dispatches(r["workdir"])
    assert os.path.isdir(os.path.join(ctx.run_dir, "trials"))
    assert not os.path.exists(os.path.join(ctx.run_dir, "trials.tar.gz"))


def test_cleanup_error_is_recorded_not_raised(tmp_path):
    r = simulate_dispatch(
        "scd.assaylib.testing.exercise",
        {"n": 1},
        fake_trial=lambda t: True,
        workdir=str(tmp_path),
        how_cleanup_success="lambda *args, **kwargs: 1 / 0",
    )
    assert r["completed"]["outcome"] == "succeeded"
    (ctx,) = load_dispatches(r["workdir"])
    events = ctx.wdhooks.read_dispatch_telemetry(r["workdir"])
    (e,) = [e for e in events if e["event"] == "cleanup_error"]
    assert e["hook"] == "success" and "ZeroDivisionError" in e["error"]
