import json
import os
import subprocess
import tempfile
import threading

TAG = "!!!screendoor:"
STDERR_TAIL_BYTES = 4000


def latest_request(submissions: list, trial_uuid: str) -> dict:
    """The trial's latest ``requested`` submission."""
    requests = [
        e
        for e in submissions
        if e["event"] == "requested" and e.get("trial_uuid") == trial_uuid
    ]
    if not requests:
        raise LookupError(f"trial {trial_uuid} was never requested")
    return max(requests, key=lambda e: e["attempt"])


class _TagCollector:
    """Collects the tagged lines of one trial; fed from two threads."""

    def __init__(self, ctx, trial_uuid: str, attempt: int):
        self.ctx, self.trial_uuid, self.attempt = ctx, trial_uuid, attempt
        self.result = None  # null unless the script sends one
        self.channels: dict[str, list] = {}
        self.malformed = 0  # tagged lines whose JSON did not parse
        self.lock = threading.Lock()

    def feed(self, line: str) -> None:
        if not line.startswith(TAG):
            return
        channel, _, payload = line[len(TAG) :].rstrip("\r\n").partition(" ")
        if not channel:
            return
        try:
            value = json.loads(payload)
        except ValueError:
            with self.lock:
                self.malformed += 1
            self.ctx.hook("how_write_trial_telemetry")(
                self.ctx,
                {
                    "event": "malformed",
                    "trial_uuid": self.trial_uuid,
                    "attempt": self.attempt,
                    "channel": channel,
                    "line": line.rstrip()[:1000],
                },
            )
            return
        with self.lock:
            if channel == "payload":  # the result; last one wins
                self.result = value
            else:
                self.channels.setdefault(channel, []).append(value)
        if channel == "telemetry":
            self.ctx.hook("how_write_trial_telemetry")(
                self.ctx,
                {
                    "event": "telemetry",
                    "trial_uuid": self.trial_uuid,
                    "attempt": self.attempt,
                    "value": value,
                },
            )


def _pump(stream, out_path: str, collector: _TagCollector) -> None:
    with open(out_path, "ab") as out:
        for raw in iter(stream.readline, b""):
            out.write(raw)
            out.flush()
            collector.feed(raw.decode(errors="replace"))


def _tail(path: str) -> str:
    with open(path, "rb") as fh:
        fh.seek(max(0, os.path.getsize(path) - STDERR_TAIL_BYTES))
        return fh.read().decode(errors="replace")


def run_trial(ctx, trial_uuid: str) -> None:
    """Run one trial to completion and record how it ended.

    The script runs in a fresh temporary directory, deleted afterwards;
    its ``cmd.sh`` and its stdout and stderr (per attempt) are kept in the
    trial directory, ``$SCREENDOOR_TRIAL_DIR``. ``started`` goes to
    telemetry; the trial payload is ``completed`` or ``failed``.
    """
    request = latest_request(ctx.read_trial_submissions(), trial_uuid)
    attempt = request["attempt"]
    cmd = request["request"]["cmd"]
    trial_dir = ctx.trial_dir(trial_uuid)
    attempt_dir = os.path.join(trial_dir, f"attempt-{attempt}")
    os.makedirs(attempt_dir, exist_ok=True)
    base = {
        "trial_uuid": trial_uuid,
        "attempt": attempt,
        "task_id": request.get("task_id"),
    }
    ctx.hook("how_write_trial_telemetry")(
        ctx,
        {
            "event": "started",
            **base,
            "pid": os.getpid(),
            "host": os.uname().nodename,
        },
    )
    script = os.path.join(trial_dir, "cmd.sh")
    with open(script, "w", encoding="utf-8") as fh:
        fh.write(cmd if cmd.endswith("\n") else cmd + "\n")
    with tempfile.TemporaryDirectory(prefix="screendoor-trial-") as scratch:
        code, collector = _run_script(ctx, request, script, scratch)
    base.update(channels=collector.channels, malformed=collector.malformed)
    if code == 0:
        ctx.write_trial_payload(
            {"event": "completed", **base, "result": collector.result}
        )
    else:
        ctx.write_trial_payload(
            {
                "event": "failed",
                **base,
                "kind": "error",
                "exit_code": code,
                "stderr_tail": _tail(_attempt_path(ctx, request, "stderr")),
            },
        )


def _attempt_path(ctx, request: dict, stream: str) -> str:
    attempt_dir = os.path.join(
        ctx.trial_dir(request["trial_uuid"]), f"attempt-{request['attempt']}"
    )
    return os.path.join(attempt_dir, f"{stream}.txt")


def _run_script(ctx, request: dict, script: str, scratch: str):
    """Run ``script`` with ``scratch`` as its working directory."""
    trial_uuid, attempt = request["trial_uuid"], request["attempt"]
    env = request["request"]["env"]
    trial_dir = ctx.trial_dir(trial_uuid)
    proc = subprocess.Popen(
        ["bash", script],
        cwd=scratch,
        env={
            **os.environ,
            **env,
            "SCREENDOOR_TRIAL_DIR": trial_dir,
            "SCREENDOOR_WORKDIR": ctx.workdir,
            "SCREENDOOR_ATTEMPT": str(attempt),
        },
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    collector = _TagCollector(ctx, trial_uuid, attempt)
    threads = [
        threading.Thread(target=_pump, args=(stream, path, collector))
        for stream, path in (
            (proc.stdout, _attempt_path(ctx, request, "stdout")),
            (proc.stderr, _attempt_path(ctx, request, "stderr")),
        )
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return proc.wait(), collector
