import shlex

PREAMBLE = """\
mkdir -p {script_dir} {log_dir}
cp "$0" {script_dir}/"$SLURM_JOB_ID".sh
exec > >(tee -a {log_dir}/"$SLURM_JOB_ID".txt) 2>&1
"""


def _quote_dir(path: str) -> str:
    """Quote ``path``, leaving a leading ``~/`` for the shell to expand."""
    if path.startswith("~/"):
        return "~/" + shlex.quote(path[2:])
    return shlex.quote(path)


def render_preamble(
    script_dir: str = "~/slurmscripts", log_dir: str = "~/slurmlogs"
) -> str:
    """Render the lines that keep a job's own script and log."""
    return PREAMBLE.format(
        script_dir=_quote_dir(script_dir), log_dir=_quote_dir(log_dir)
    )


def render_sbatch(
    ctx,
    name: str,
    batches: list,
    *,
    worker: str,
    script_dir: str = "~/slurmscripts",
    log_dir: str = "~/slurmlogs",
) -> str:
    """Render one array-job script, named ``name``; task i runs batch i."""
    timeout = ctx.record["trial_batch_timeout"]
    cases = [
        f'  {i}) TRIALS="{" ".join(e["trial_uuid"] for e in batch)}" ;;'
        for i, batch in enumerate(batches)
    ]
    lines = [
        "#!/bin/bash",
        f"#SBATCH --job-name={name}",
        f"#SBATCH --array=0-{len(batches) - 1}",
        "#SBATCH --output=/dev/null",
        # whole minutes, rounded up
        *([f"#SBATCH --time={-(-int(timeout) // 60)}"] if timeout else []),
        "set -uo pipefail",
        render_preamble(script_dir, log_dir).rstrip("\n"),
        'case "$SLURM_ARRAY_TASK_ID" in',
        *cases,
        '  *) echo "unknown array task" >&2; exit 1 ;;',
        "esac",
        f"exec {worker} --workdir {shlex.quote(ctx.workdir)} "
        f"--dispatch {ctx.dispatch_uuid} $TRIALS",
    ]
    return "\n".join(lines) + "\n"
