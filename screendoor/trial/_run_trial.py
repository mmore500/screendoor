import json
import logging
import os
import subprocess
import tempfile
import threading

TAG = "!!!screendoor:"
PIPE_GRACE_S = 10  # how long output may trail the script's exit


def latest_request(submissions: list, trial_uuid: str) -> dict:
    """The trial's latest ``requested`` submission."""
    requests = [
        e
        for e in submissions
        if e["event"] == "requested" and e["trial_uuid"] == trial_uuid
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
        self.lock = threading.Lock()

    def feed(self, line: str) -> None:
        if not line.startswith(TAG):
            return
        channel, _, text = line[len(TAG) :].rstrip("\r\n").partition(" ")
        try:
            value = json.loads(text)
        except ValueError:
            logging.warning("screendoor: ignoring bad JSON: %.200s", line)
            return
        with self.lock:
            if channel == "payload":  # the result; last one wins
                self.result = value
            else:
                self.channels.setdefault(channel, []).append(value)
        if channel == "telemetry":
            self.ctx.write_trial_telemetry(
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


def run_trial(ctx, trial_uuid: str, submissions: list | None = None) -> None:
    """Run one trial to completion and record how it ended.

    The script runs in a fresh temporary directory, deleted afterwards;
    ``cmd.sh`` and, per attempt, ``attempt-<n>/stdout.txt`` and
    ``stderr.txt`` are kept in the trial directory,
    ``$SCREENDOOR_TRIAL_DIR``. ``started`` goes to trial telemetry; the
    trial payload is ``completed``, with the script's result, if it
    exited 0, else ``failed``. ``submissions`` saves re-reading the trial
    submissions for each trial of a batch.
    """
    if submissions is None:
        submissions = ctx.read_trial_submissions()
    request = latest_request(submissions, trial_uuid)
    attempt = request["attempt"]
    trial_dir = ctx.trial_dir(trial_uuid)
    attempt_dir = os.path.join(trial_dir, f"attempt-{attempt}")
    os.makedirs(attempt_dir, exist_ok=True)
    base = {
        "trial_uuid": trial_uuid,
        "attempt": attempt,
        "task_id": request["task_id"],
    }
    ctx.write_trial_telemetry(
        {
            "event": "started",
            **base,
            "pid": os.getpid(),
            "host": os.uname().nodename,
        },
    )
    script = os.path.join(trial_dir, "cmd.sh")
    with open(script, "w", encoding="utf-8") as fh:
        fh.write(request["request"]["cmd"].rstrip("\n") + "\n")
    env = {
        **os.environ,
        **request["request"]["env"],
        "SCREENDOOR_TRIAL_DIR": trial_dir,
        "SCREENDOOR_DISPATCHDIR": ctx.dispatchdir,
        "SCREENDOOR_ATTEMPT": str(attempt),
    }
    collector = _TagCollector(ctx, trial_uuid, attempt)
    with tempfile.TemporaryDirectory(
        prefix="screendoor-trial-", ignore_cleanup_errors=True
    ) as scratch:
        code = _run_script(script, scratch, env, attempt_dir, collector)
    base.update(exit_code=code, channels=collector.channels)
    if code == 0:
        ctx.write_trial_payload(
            {"event": "completed", **base, "result": collector.result}
        )
    else:
        ctx.write_trial_payload({"event": "failed", **base})


def _run_script(script, cwd, env, attempt_dir, collector) -> int:
    """Run ``script``, logging and scanning its output; return its exit
    code."""
    proc = subprocess.Popen(
        ["bash", script],
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    threads = [
        threading.Thread(
            target=_pump,
            args=(stream, os.path.join(attempt_dir, f"{name}.txt"), collector),
            daemon=True,
        )
        for name, stream in (("stdout", proc.stdout), ("stderr", proc.stderr))
    ]
    for thread in threads:
        thread.start()
    code = proc.wait()
    for thread in threads:  # a child left holding a pipe can't stall us
        thread.join(timeout=PIPE_GRACE_S)
    return code
