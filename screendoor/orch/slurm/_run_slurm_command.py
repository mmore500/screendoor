import subprocess


def run(argv: list[str]) -> str:
    """Run a Slurm command and return its stdout; tests replace this.

    Parameters
    ----------
    argv : list of str
        The command and its arguments.

    Returns
    -------
    str
        The command's stdout.

    Raises
    ------
    RuntimeError
        If the command exits nonzero.
    """
    proc = subprocess.run(argv, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"{' '.join(argv)} exited {proc.returncode}: {proc.stderr.strip()}"
        )
    return proc.stdout


def queued_jobs() -> dict[tuple[str, int | None], str]:
    """List the user's queued and running jobs, as `{(name, array index):
    job id}`.

    Each array task has its own entry; a job that is not an array has
    index None.

    Returns
    -------
    dict of {(str, int or None): str}
        The job id of each queued or running array task, by job name and
        index.

    Raises
    ------
    RuntimeError
        If `squeue` fails.
    """
    out = run(["squeue", "--me", "--noheader", "--array", "--format=%i|%j|%K"])
    jobs = {}
    for line in out.splitlines():
        job_id, name, index = line.strip().split("|")
        jobs[name, int(index) if index.isdigit() else None] = job_id
    return jobs
