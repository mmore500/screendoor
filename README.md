# screendoor

[
![PyPI](https://img.shields.io/pypi/v/screendoor.svg)
](https://pypi.python.org/pypi/screendoor)
[
![Python versions](https://img.shields.io/pypi/pyversions/screendoor.svg)
](https://pypi.python.org/pypi/screendoor)
[
![CI](https://github.com/mmore500/screendoor/actions/workflows/ci.yaml/badge.svg)
](https://github.com/mmore500/screendoor/actions)
[
![License](https://img.shields.io/github/license/mmore500/screendoor.svg)
](https://github.com/mmore500/screendoor/blob/master/LICENSE)
[
![GitHub stars](https://img.shields.io/github/stars/mmore500/screendoor.svg?style=round-square&logo=github&label=Stars&logoColor=white)](https://github.com/mmore500/screendoor)

> [!WARNING]
> screendoor is experimental. It may produce incorrect results, and its interface is subject to change.

screendoor runs *dynamic screens*: searches over trials (knockouts, ablations, parameter sweeps) where the next trials depend on the results of earlier ones, on a workstation or a Slurm cluster, with no database, broker or server.

- Free software: MIT
- Repository: <https://github.com/mmore500/screendoor>

A daemon wakes on a cron schedule, rebuilds state from append-only JSONL records, asks the assay's `churn` function what to do next, and carries out the actions it returns.
The records are the state: kill the daemon at any moment; start it again and the dispatch resumes.
Churn is pure: records in, actions out.
Every side effect is a hook, and no hook has a default: a dispatch sets all of its hooks; the dispatchdir's `screendoor.json` sets the daemon's.

screendoor is standard library only, Python 3.10+.
Built-in assays cover smoke tests, potentiation scans and skeletonization (jenga, ddmin, Minesweeper, hybrid and GAMA); see [docs/skeletonization.md](docs/skeletonization.md).
Trials run as local processes or as Slurm array jobs.
See [docs/guide.md](docs/guide.md) for writing assays, every dispatch setting and hook, trials, the daemon, storage and orchestrators.

## Usage

```bash
mkdir -p work && cat > work/screendoor.json <<'JSON'
{
  "how_read_dispatch_submissions": "scd.record.appendjsonl.read_dispatch_submissions()",
  "how_write_dispatch_submissions": "scd.record.appendjsonl.write_dispatch_submissions()",
  "how_read_dispatch_payloads": "scd.record.appendjsonl.read_dispatch_payloads()",
  "how_write_dispatch_payloads": "scd.record.appendjsonl.write_dispatch_payloads()",
  "how_read_dispatch_telemetry": "scd.record.appendjsonl.read_dispatch_telemetry()",
  "how_write_dispatch_telemetry": "scd.record.appendjsonl.write_dispatch_telemetry()",
  "how_log_info": "logging.info",
  "how_notify_liveness": "scd.notify.null.notify()",
  "how_notify_termination": "scd.notify.log.notify()"
}
JSON
python3 -m screendoor.daemon.submit_dispatch - --dispatchdir work <<JSON
{
  "meta_project": "default",
  "meta_experiment": "default",
  "meta_treatment": "default",
  "meta_user": "$(id -un)",
  "meta_redo": "0",
  "meta_seed": 1,
  "assay": "scd.churn.seed_global_rngs(scd.assaylib.testing.exercise)",
  "assay_kwargs": {"n": 4, "cmd": "echo \"!!!screendoor:payload \$((i * i))\""},
  "schedule": "* * * * *",
  "how_launch": "scd.orch.subprocess.launch()",
  "how_poke": "scd.orch.subprocess.poke()",
  "how_kill": "scd.orch.subprocess.kill()",
  "how_throttle_churn": "scd.orch.subprocess.throttle(max_procs=4)",
  "how_setup": "scd.record.appendjsonl.setup()",
  "how_read_trial_submissions": "scd.record.appendjsonl.read_trial_submissions()",
  "how_write_trial_submissions": "scd.record.appendjsonl.write_trial_submissions()",
  "how_read_trial_payloads": "scd.record.appendjsonl.read_trial_payloads()",
  "how_write_trial_payloads": "scd.record.appendjsonl.write_trial_payloads()",
  "how_prep_trial_payloads": "scd.record.appendjsonl.prep_trial_payloads()",
  "how_read_trial_telemetry": "scd.record.appendjsonl.read_trial_telemetry()",
  "how_write_trial_telemetry": "scd.record.appendjsonl.write_trial_telemetry()",
  "how_read_churn_memo": "scd.record.appendjsonl.read_churn_memo()",
  "how_write_churn_memo": "scd.record.appendjsonl.write_churn_memo()",
  "how_read_churn_notify": "scd.record.appendjsonl.read_churn_notify()",
  "how_write_churn_notify": "scd.record.appendjsonl.write_churn_notify()",
  "how_notify_progress": "scd.notify.log.notify()",
  "how_notify_eta": "scd.notify.log.notify()",
  "how_notify_success": "scd.notify.log.notify()",
  "how_notify_failure": "scd.notify.log.notify()",
  "how_notify_warning": "scd.notify.log.notify()",
  "how_notify_anomaly": "scd.notify.log.notify()",
  "how_unblock_churn": "scd.unblock.all_trials_ready()",
  "how_cleanup_success": "scd.cleanup.tar(clear=True)",
  "how_cleanup_failure": "lambda ctx, completed: None"
}
JSON
python3 -m screendoor.daemon.run_busyloop --dispatchdir work
python3 -m screendoor.daemon.print_status --dispatchdir work
```

`screendoor.json` holds the daemon's own hooks. The dispatch has labels,
an assay with its kwargs, a cron `schedule` and its hooks; the smoke-test
assay here launches `n` trials of `cmd`, each with `$i` in its env, and
succeeds with what they sent. The second heredoc is unquoted so the shell
fills in `meta_user`, so the trial script's `$` is written `\$`.
Submitting only records the dispatch; `run_busyloop` runs it, ticking
until nothing is open. `print_status` then shows it `succeeded` with
results `[0, 1, 4, 9]`, and `work/` holds:

```
work/
  screendoor.json
  dispatch_submissions.jsonl  dispatch_payloads.jsonl  dispatch_telemetry.jsonl
  dispatch_notify.jsonl       dispatch_log.txt
  project=default/
    date=2026-11-12+what=default%default%1+redo=0/
      trial_submissions.jsonl  trial_payloads.jsonl  trial_telemetry.jsonl
      churn_notify.jsonl
      jobs/            # the local processes' pidfiles and logs
      trials.tar.gz    # trials/ (cmd.sh, stdout, stderr), archived on success
```

`python3 -m screendoor` lists every command.

## Installation

```bash
python3 -m pip install screendoor
```

From source:

```bash
git clone https://github.com/mmore500/screendoor
python3 -m pip install ./screendoor
```

On a cluster, the daemon can run from the container image:

```bash
apptainer exec docker://ghcr.io/mmore500/screendoor:v0.1.0 \
  python3 -m screendoor.daemon.run_tick_once --dispatchdir .
eval "$(apptainer exec docker://ghcr.io/mmore500/screendoor:v0.1.0 \
  cat /opt/screendoor/slurm-binds.sh | sh)"
```

The worker runs on the host. Where screendoor isn't installed, point the
launcher at the `.pyz` attached to each
[GitHub release](https://github.com/mmore500/screendoor/releases):
`scd.orch.slurm.launch(worker="python3 /shared/screendoor-0.1.0.pyz worker")`.

## AI Use

Substantial portions of screendoor were prepared using agentic coding tools.
