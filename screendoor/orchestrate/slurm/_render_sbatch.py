import json
import shlex

PREAMBLE = """\
mkdir -p {script_dir} {log_dir}
cp "$0" {script_dir}/"$SLURM_JOB_ID".sh
exec > >(tee -a {log_dir}/"$SLURM_JOB_ID".txt) 2>&1
"""
BATCHES_MARK = "# screendoor-batches: "


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


def job_name(launch_id: str) -> str:
    return f"screendoor-{launch_id}"


def render_sbatch(
    ctx,
    batches: list,
    launch_id: str,
    *,
    worker: str,
    script_dir: str = "~/slurmscripts",
    log_dir: str = "~/slurmlogs",
) -> str:
    """Render one array-job script; array task i runs batch i."""
    timeout = ctx.record["trial_batch_timeout"]
    cases = [
        f'  {i}) TRIALS="{" ".join(e["trial_uuid"] for e in batch)}" ;;'
        for i, batch in enumerate(batches)
    ]
    lines = [
        "#!/bin/bash",
        f"#SBATCH --job-name={job_name(launch_id)}",
        f"#SBATCH --array=0-{len(batches) - 1}",
        "#SBATCH --output=/dev/null",
        # whole minutes, rounded up
        *([f"#SBATCH --time={-(-int(timeout) // 60)}"] if timeout else []),
        BATCHES_MARK + json.dumps(batches),
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


def parse_batches(script: str) -> list | None:
    """Recover the batches from a script that render_sbatch wrote."""
    for line in script.splitlines():
        if line.startswith(BATCHES_MARK):
            return json.loads(line[len(BATCHES_MARK) :])
    return None
