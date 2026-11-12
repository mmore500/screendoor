import json
import logging
import os
import subprocess
import threading

from .auxlib._DispatchContext import load_dispatches
from .rng._trial_seed import trial_seed

TAG = "!!!screendoor:"
STDERR_TAIL_BYTES = 4000


def latest_request(events: list, trial_uuid: str) -> dict:
    """The trial's latest ``requested`` event."""
    requests = [
        e
        for e in events
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
            self.ctx.hook("how_write_telemetry")(
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
            if channel == "result":  # last one wins
                self.result = value
            else:
                self.channels.setdefault(channel, []).append(value)
        if channel == "telemetry":
            self.ctx.hook("how_write_telemetry")(
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
    """Run one trial to completion and record how it ended."""
    write = ctx.hook("how_write_payload")
    request = latest_request(
        ctx.hook("how_read_payload")(ctx, raw=True), trial_uuid
    )
    attempt = request["attempt"]
    cmd, env = request["request"]["cmd"], request["request"]["env"]
    trial_dir = ctx.trial_dir(trial_uuid)
    attempt_dir = os.path.join(trial_dir, f"attempt-{attempt}")
    os.makedirs(attempt_dir, exist_ok=True)
    base = {
        "trial_uuid": trial_uuid,
        "attempt": attempt,
        "task_id": request.get("task_id"),
    }
    write(
        ctx,
        {
            "event": "started",
            **base,
            "pid": os.getpid(),
            "host": os.uname().nodename,
        },
    )
    with open(os.path.join(trial_dir, "cmd.sh"), "w", encoding="utf-8") as fh:
        fh.write(cmd if cmd.endswith("\n") else cmd + "\n")
    proc = subprocess.Popen(
        ["bash", "cmd.sh"],
        cwd=trial_dir,
        env={
            **os.environ,
            **env,
            "SCREENDOOR_SEED": str(trial_seed(ctx.seed, trial_uuid)),
            "SCREENDOOR_TRIAL_DIR": trial_dir,
            "SCREENDOOR_WORKDIR": ctx.workdir,
            "SCREENDOOR_ATTEMPT": str(attempt),
        },
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    collector = _TagCollector(ctx, trial_uuid, attempt)
    stderr_path = os.path.join(attempt_dir, "stderr.txt")
    threads = [
        threading.Thread(target=_pump, args=(stream, path, collector))
        for stream, path in (
            (proc.stdout, os.path.join(attempt_dir, "stdout.txt")),
            (proc.stderr, stderr_path),
        )
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    code = proc.wait()
    base.update(channels=collector.channels, malformed=collector.malformed)
    if code == 0:
        write(ctx, {"event": "completed", **base, "result": collector.result})
    else:
        write(
            ctx,
            {
                "event": "failed",
                **base,
                "kind": "error",
                "exit_code": code,
                "stderr_tail": _tail(stderr_path),
            },
        )


def worker(workdir: str, dispatch_uuid: str, trials: list) -> int:
    """Run trials (uuids or trial directories) one after another.

    Returns a process exit code.
    """
    ctxs = {c.dispatch_uuid: c for c in load_dispatches(workdir)}
    if dispatch_uuid not in ctxs:
        raise LookupError(f"no dispatch {dispatch_uuid} in {workdir}")
    exit_code = 0
    for trial in trials:
        trial_uuid = os.path.basename(os.path.normpath(trial))
        try:
            run_trial(ctxs[dispatch_uuid], trial_uuid)
        except Exception:
            logging.exception("screendoor: trial %s crashed", trial_uuid)
            exit_code = 1
    return exit_code
