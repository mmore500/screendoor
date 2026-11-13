import os
import shlex
import subprocess
import time
import typing

from ...auxlib._default_python_command import default_python_command
from ._procs import job_dir, read_pidfile


def launch(
    *, worker: str | None = None, pidfile_wait_s: float = 30.0
) -> typing.Callable[[dict, str, list[list[dict]]], None]:
    """Create a `how_launch` hook that runs each batch as a detached local
    process, under coreutils `timeout` if the dispatch sets
    `trial_batch_timeout`.

    Batch `i` of job `name` writes `jobs/<name>/<i>.pid` in the run
    directory as it starts, which is how `poke`, `kill` and `throttle` find
    it.

    Parameters
    ----------
    worker : str or None, default None
        The command that starts the worker; None uses this interpreter's,
        from `default_python_command`.
    pidfile_wait_s : float, default 30.0
        Seconds to wait for each batch to write its pidfile.

    Returns
    -------
    Callable[[dict, str, list[list[dict]]], None]
        Hook `launch(ctx, name, batches)`, which starts each batch and
        waits until all have written their pidfiles, raising `RuntimeError`
        if one has not within `pidfile_wait_s`.
    """
    worker = worker or f"{default_python_command()} -m screendoor.trial.worker"

    def launch(ctx: dict, name: str, batches: list[list[dict]]) -> None:
        jdir = job_dir(ctx, name)
        os.makedirs(jdir, exist_ok=True)
        timeout = ctx["dispatch"]["trial_batch_timeout"]
        dispatchdir = shlex.quote(ctx["dispatchdir"])
        prefix = f"timeout {int(timeout)} " if timeout else ""
        pidfiles = []
        for i, batch in enumerate(batches):
            pidfile = os.path.join(jdir, f"{i}.pid")
            pidfiles.append(pidfile)
            log = shlex.quote(os.path.join(jdir, f"{i}.log"))
            uuids = " ".join(e["trial_uuid"] for e in batch)
            q = shlex.quote(pidfile)
            # pid and start time (field 22 of /proc/<pid>/stat, after comm)
            stamp = (
                "p=$BASHPID; echo $p $(sed 's/.*) //' /proc/$p/stat "
                "| cut -d' ' -f20)"
                if os.path.isdir("/proc")
                else "echo $BASHPID 0"
            )
            script = (
                f"( {stamp} > {q}.tmp && mv {q}.tmp {q} && "
                f"exec {prefix}{worker} --dispatchdir {dispatchdir} "
                f"--dispatch {ctx['dispatch_uuid']} {uuids} "
                f") </dev/null >>{log} 2>&1 &"
            )
            # its own session, so that kill can signal the whole batch
            subprocess.run(
                ["bash", "-c", script], check=True, start_new_session=True
            )
        deadline = time.monotonic() + pidfile_wait_s
        for pidfile in pidfiles:  # so that the next poke can see each one
            while read_pidfile(pidfile) is None:
                if time.monotonic() > deadline:
                    raise RuntimeError(f"process for {pidfile} never started")
                time.sleep(0.01)

    return launch
