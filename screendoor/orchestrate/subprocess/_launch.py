import json
import os
import shlex
import subprocess
import time

from ...auxlib._batch_trials import batch_trials
from ...auxlib._default_python_command import default_python_command
from ._procs import launch_dir, read_pidfile


def launch(*, worker: str | None = None, pidfile_wait_s: float = 30.0):
    """Run each batch as a detached local process, under ``timeout``.

    ``worker`` is the command that starts the worker; by default, this
    interpreter's.
    """
    worker = worker or f"{default_python_command()} -m screendoor.worker"

    def launch(ctx, entries: list, launch_id: str) -> list:
        ldir = launch_dir(ctx, launch_id)
        os.makedirs(ldir, exist_ok=True)
        batches = batch_trials(entries, ctx.record["trial_batchsize"])
        with open(os.path.join(ldir, "batches.json"), "w") as fh:
            json.dump(batches, fh)
        timeout = ctx.record["trial_batch_timeout"]
        prefix = f"timeout {int(timeout)} " if timeout else ""
        for i, batch in enumerate(batches):
            pidfile = shlex.quote(os.path.join(ldir, f"{i}.pid"))
            log = shlex.quote(os.path.join(ldir, f"{i}.log"))
            uuids = " ".join(e["trial_uuid"] for e in batch)
            script = (
                f"( echo $BASHPID > {pidfile}.tmp && "
                f"mv {pidfile}.tmp {pidfile} && "
                f"exec {prefix}{worker} --workdir {shlex.quote(ctx.workdir)} "
                f"--dispatch {ctx.dispatch_uuid} {uuids} "
                f") </dev/null >>{log} 2>&1 &"
            )
            # its own session, so that kill can signal the whole batch
            subprocess.run(
                ["bash", "-c", script], check=True, start_new_session=True
            )
        launched = []
        deadline = time.monotonic() + pidfile_wait_s
        for i, batch in enumerate(batches):
            pidfile = os.path.join(ldir, f"{i}.pid")
            while (job := read_pidfile(pidfile)) is None:
                if time.monotonic() > deadline:
                    raise RuntimeError(f"process for {pidfile} never started")
                time.sleep(0.01)
            launched += [{**e, "job_id": job} for e in batch]
        return launched

    def adopt(ctx, launch_id: str, entries: list) -> dict:
        """Find processes an interrupted launch call already started.

        Returns ``{(trial_uuid, attempt): job_id}``.
        """
        ldir = launch_dir(ctx, launch_id)
        try:
            with open(os.path.join(ldir, "batches.json")) as fh:
                batches = json.load(fh)
        except (OSError, ValueError):
            return {}
        found = {}
        for i, batch in enumerate(batches):
            job = read_pidfile(os.path.join(ldir, f"{i}.pid"))
            for e in batch if job else ():
                found[e["trial_uuid"], e["attempt"]] = job
        return found

    launch.adopt = adopt
    return launch
