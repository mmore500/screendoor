import hashlib
import os
import shlex

from ...orch.slurm._render_sbatch import render_preamble


def chain_job_name(dispatchdir: str) -> str:
    """Name the daemon jobs of `dispatchdir`, which all share one name.

    Parameters
    ----------
    dispatchdir : str
        Path of the daemon's dispatchdir.

    Returns
    -------
    str
        `screendoor-daemon-<digest of the dispatchdir's absolute path>`.
    """
    digest = hashlib.sha256(os.path.abspath(dispatchdir).encode()).hexdigest()
    return f"screendoor-daemon-{digest[:8]}"


def render_daemon_sbatch(
    dispatchdir: str,
    *,
    python: str,
    sbatch_flags: str = "",
    script_dir: str = "~/slurmscripts",
    log_dir: str = "~/slurmlogs",
) -> str:
    """Render the script of one daemon job, which queues its successor and
    then ticks once.

    The successor is timed by its own `--begin`, not by waiting for this
    job to end.

    Parameters
    ----------
    dispatchdir : str
        Path of the daemon's dispatchdir.
    python : str
        The command that runs python with screendoor importable.
    sbatch_flags : str, default ""
        Extra sbatch flags, as one shell string, passed on to the
        successor.
    script_dir : str, default "~/slurmscripts"
        Where the job keeps a copy of its script.
    log_dir : str, default "~/slurmlogs"
        Where the job writes its log.

    Returns
    -------
    str
        The sbatch script.
    """
    wd = shlex.quote(os.path.abspath(dispatchdir))
    lines = [
        "#!/bin/bash",
        f"#SBATCH --job-name={chain_job_name(dispatchdir)}",
        "#SBATCH --signal=B:USR1@300",
        "#SBATCH --output=/dev/null",
        "set -uo pipefail",
        render_preamble(script_dir, log_dir).rstrip("\n"),
        f"{python} -m screendoor.daemon.slurm.submit_daemon --successor "
        f"--dispatchdir {wd} --python {shlex.quote(python)} "
        f"--sbatch-flags {shlex.quote(sbatch_flags)} "
        f"--script-dir {shlex.quote(script_dir)} "
        f"--log-dir {shlex.quote(log_dir)}",
        # tick in the background and wait, so that bash can forward USR1
        f"{python} -m screendoor.daemon.run_tick_once --dispatchdir {wd} &",
        "child=$!",
        "trap 'kill -USR1 $child' USR1",
        "wait $child; wait $child",
    ]
    return "\n".join(lines) + "\n"
