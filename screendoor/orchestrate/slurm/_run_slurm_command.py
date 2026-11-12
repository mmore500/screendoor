import subprocess


def run(argv: list) -> str:
    """Run a Slurm command and return its stdout; tests replace this."""
    proc = subprocess.run(argv, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"{' '.join(argv)} exited {proc.returncode}: {proc.stderr.strip()}"
        )
    return proc.stdout


def queued_job_ids() -> set:
    """Ids of your queued and running jobs, one per array task."""
    return set(
        run(["squeue", "--me", "--noheader", "--array", "--format=%i"]).split()
    )
