import os

from screendoor.auxlib._DispatchContext import load_dispatches
from screendoor.testing import simulate_dispatch


def run(cmd):
    """Run ``cmd`` as one real trial; return the trial and its context."""
    r = simulate_dispatch(
        "scd.assaylib.testing.exercise", {"n": 1, "cmd": cmd}
    )
    (ctx,) = load_dispatches(r["workdir"])
    return r["trials"][0], ctx


def test_tags_and_channels():
    t, ctx = run(
        "echo '!!!screendoor:telemetry {\"e\": 1}'\n"
        "echo '!!!screendoor:telemetry {\"e\": 2}' >&2\n"
        "echo '!!!screendoor:custom [1,2]'\n"
        "echo '!!!screendoor:result 1'\n"
        "echo '!!!screendoor:result {\"final\": true}'\n"
    )
    assert t["status"] == "succeeded"
    assert t["result"] == {"final": True}  # last one wins
    assert sorted(x["e"] for x in t["channels"]["telemetry"]) == [1, 2]
    assert t["channels"]["custom"] == [[1, 2]]
    assert len(ctx.hook("how_read_telemetry")(ctx)) == 2


def test_malformed_lines_go_to_telemetry():
    t, ctx = run(
        "echo '!!!screendoor:telemetry {nope'\n"
        "echo '!!!screendoor:result {nope'\n"
        "echo '!!!screendoor:result 7'\n"
    )
    assert (t["status"], t["result"], t["malformed"]) == ("succeeded", 7, 2)
    events = ctx.hook("how_read_telemetry")(ctx)
    assert [e["event"] for e in events] == ["malformed", "malformed"]
    assert [e["channel"] for e in events] == ["telemetry", "result"]


def test_no_result_is_null():
    for cmd in ("echo hi", "echo '!!!screendoor:result {nope'"):
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
    t, _ = run("echo '!!!screendoor:result 1'; false")
    assert t["error"]["kind"] == "error"


def test_trial_dir_layout():
    t, ctx = run("echo '!!!screendoor:result 1'; echo out; echo err >&2")

    def read(*parts):
        with open(os.path.join(ctx.trial_dir(t["trial_uuid"]), *parts)) as fh:
            return fh.read()

    assert read("cmd.sh").startswith("echo")
    assert "out" in read("attempt-0", "stdout.txt")
    assert "err" in read("attempt-0", "stderr.txt")
