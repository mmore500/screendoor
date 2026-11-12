# screendoor

screendoor runs *dynamic screens*: searches over trials (knockouts, ablations,
parameter sweeps) where the next trials depend on the results of earlier
ones. A daemon wakes on a cron schedule, rebuilds state from append-only JSONL
records, asks the assay's `churn` function what to do next, and carries out
the actions it returns.

* **The records are the state.** Kill the daemon at any moment; start it
  again and the dispatch resumes.
* **Assays are pure.** `churn(dispatch, trial_submissions, trial_payloads,
  memo) -> actions`, given the raw trial records;
  `scd.churn.fold_trials(trial_submissions, trial_payloads)` folds them into
  one dict per trial. Wrap an assay in `scd.churn.seed_global_rngs(...)` to
  draw from seeded global RNGs.
* **Every side effect is a hook** (`how_launch`, `how_poke`, `how_throttle`,
  `how_unblock_churn`, `how_cleanup_*`, `how_notify_*`,
  `how_read_*`/`how_write_*`), each with a default.
* **Trials are shell scripts** that print `!!!screendoor:result <json>`.
* **Standard library only**, Python 3.10+. No database, broker or server.
* **screendoor never kills anything.** Timeouts belong to the orchestrator.

## Quick start

```bash
ruby -ryaml -rjson -e 'puts JSON.generate(YAML.safe_load(ARGF.read))' <<YAML \
  | python3 -m screendoor.daemon.submit_dispatch - --workdir work
meta_project: default
meta_experiment: default
meta_treatment: default
meta_user: "$(id -un)"
meta_attempt: "$(date)"
meta_seed: 1
assay: scd.churn.seed_global_rngs(scd.assaylib.testing.exercise)
assay_kwargs:
  n: 4
  cmd: |
    set -euo pipefail
    echo "!!!screendoor:result \$((i * i))"
schedule: "* * * * *"
how_launch: scd.orch.subprocess.launch()
how_poke: scd.orch.subprocess.poke()
YAML
python3 -m screendoor.daemon.run_busyloop --workdir work
python3 -m screendoor.daemon.print_status --workdir work
```

The heredoc delimiter is unquoted so that the shell fills in `meta_user`
and `meta_attempt`; in exchange, each `$` meant for the trial script is
written `\$`. Submitting only records the dispatch: the daemon is started
separately.

`python3 -m screendoor` lists every command. Run the daemon as a busy loop
(`run_busyloop`), from cron (`run_tick_once`), or as a self-requeueing Slurm
chain (`daemon.slurm.submit_daemon`).

## Assays

| Assay | What it does |
|---|---|
| `scd.assaylib.testing.exercise` | Smoke test: n copies of a command |
| `scd.assaylib.knockout.naive_exhaustive` | One knockout per target + baseline |
| `scd.assaylib.skeletonize.naive_jenga` | One removal per round, memo-driven |
| `scd.assaylib.skeletonize.ddmin` | Parallel partition-union delta debugging |
| `scd.assaylib.skeletonize.minesweeper` | 4-stage Minesweeper (Rees-Garbutt 2020) |
| `scd.assaylib.skeletonize.hybrid` | Multi-dose pilot + top-down ddmin / bottom-up sieve |

The three knockout-skeletonization strategies come from the 2026-11-03
`knockout_skeleton` work. See [docs/skeletonize.md](docs/skeletonize.md),
and [examples/avida](examples/avida) for running them on Avida.

## Testing

```bash
python3 -m pytest            # Avida tests run when an avida binary is found
python3 scripts/bare_exercise.py
./scripts/build_pyz.sh       # single-file dist/screendoor-<v>.pyz
```

## Deployment

```bash
apptainer exec docker://ghcr.io/mmore500/screendoor:v0.1.0 \
  python3 -m screendoor.daemon.run_tick_once --workdir .
eval "$(apptainer exec docker://ghcr.io/mmore500/screendoor:v0.1.0 \
  cat /opt/screendoor/slurm-binds.sh | sh)"
```

The worker runs on the host. Where screendoor isn't installed, point the
launcher at the release `.pyz`:
`scd.orch.slurm.launch(worker="python3 /shared/screendoor-0.1.0.pyz worker")`.

## Records

A workdir holds the dispatch records; each dispatch's run directory holds
its trial records and the rest. Submissions are what is fed in; payloads
are what comes of it.

| File | Holds | Written by |
|---|---|---|
| `dispatch_submissions.jsonl` | `submitted`: one per dispatch | `submit_dispatch` |
| `dispatch_payloads.jsonl` | `setup`, `ticked`, `churn_error`, `killed`, `resumed`, `closed`, `cleanup_error` | the daemon |
| `<run_dir>/trial_submissions.jsonl` | `requested` (one per attempt, naming its job), `killed` | the daemon |
| `<run_dir>/trial_payloads.jsonl` | `completed`, `failed`: results only | workers; the daemon for `failed: lost` |
| `<run_dir>/trial_telemetry.jsonl` | `started` (pid, host), `telemetry` values, `malformed` lines | workers |
| `<run_dir>/memo.jsonl`, `notify.jsonl` | memos, notifications | the daemon |

Each file has a `how_read_<file>` and `how_write_<file>` hook. The dispatch
hooks (`how_read_dispatch_submissions`, ...) are the daemon's own, set in
`<workdir>/screendoor.json`; the rest are per dispatch. Three storage
backends provide them:

* `scd.record.appendjsonl` (default): one `O_APPEND` write per line.
* `scd.record.lockedjsonl`: the same, but every append holds an exclusive
  `fcntl` lock and every read a shared one, for filesystems where
  `O_APPEND` alone can tear or interleave lines (NFS across nodes). Each
  hook takes `timeout=` (seconds; default, wait forever) and raises
  `LockTimeoutError` past it. An unterminated last line left by a writer
  that died mid-write is ended before the next append. A per-path thread
  lock also keeps one process's threads apart, as `fcntl` locks belong to
  the process.
* `scd.record.slottedjsonl`: trial payloads only (`read_trial_payloads`,
  `write_trial_payloads`, `prep_trial_payloads`). Each trial's payload goes
  to line `task_id` of `trial_payloads.slots.jsonl`, lock-free, in a
  fixed-size checksummed slot (Slotted JSONL v0.1: `init`, `extend`,
  `write`, `read`, `missing`, `convert`, `encode_slot`, `decode_slot`). The
  slot size is set once, as `prep_trial_payloads(slot_bytes=8192)` (a
  multiple of 4096; default 4096); the other two hooks take it from the
  file, and raise `ValueError` if given a different one. A payload too
  large for its slot is appended to `trial_payloads.jsonl` instead.

`<workdir>/screendoor-notify.jsonl` (the daemon's liveness and termination
notices) is always appended directly.

## The daemon's pass

For each open dispatch, a tick:

1. polls every unsettled trial's job (`how_poke`), and relaunches those
   whose job is gone, or records them `failed: lost` after
   `trial_maxretry` relaunches;
2. checks `how_throttle(ctx)`; when it is false, churn may still notify,
   succeed or fail, but not launch or memo;
3. calls `how_unblock_churn(ctx, trial_submissions, trial_payloads)`, and
   only if it is true, `churn`; the default,
   `scd.unblock.all_trials_ready`, waits until no submitted trial is
   outstanding. Churn is called again in the same tick after each memo.
4. on `succeed` or `fail`, records `closed` and calls
   `how_cleanup_success(ctx, closed)` or `how_cleanup_failure(ctx, closed)`.
   By default success archives `trials/` to `trials.tar.gz` and deletes it
   (`scd.cleanup.tar`, then `scd.cleanup.clear`), and failure keeps
   everything. A cleanup that raises is recorded as `cleanup_error`.

## Jobs

The daemon fixes each launch's batches and job before launching it, and
records them in every trial's `requested` submission as `job: {name,
index}`: the name is `screendoor-<dispatch8>-<hash of the trial attempts>`,
and the index is the trial's batch (its array task). So a trial's job is
known from the records alone, and nothing has to be adopted after a crash:
poke asks the orchestrator which of those jobs are live, and the rest are
relaunched. A crash between recording and launching costs one relaunch.

* `how_launch(ctx, name, batches)`: start job `name`, whose batch `i` (a
  list of `{trial_uuid, attempt}`) runs as task `i`.
* `how_poke(ctx, trials) -> {trial_uuid}`: the trials whose job is gone.
* `how_kill(ctx, trials)`: cancel the trials' jobs.
* `how_throttle(ctx) -> bool`: default `lambda *args, **kwargs: True`.

`scd.orch.slurm` submits a job as one `sbatch --array` with `--job-name`
`name` and polls with one `squeue --me --array` per tick.
`scd.orch.subprocess` runs each batch as a detached process that writes
`<run_dir>/jobs/<name>/<index>.pid` (pid and start time) as it starts.
`scd.orch.inline` runs trials in the daemon's process, for tests.

## Trials

* Worker CLI: `python3 -m screendoor.trial.worker --workdir W --dispatch U
  <trial_uuid|trial_dir>...`.
* Each trial's script runs in a fresh temporary directory, deleted when it
  ends. Its `cmd.sh` and, per attempt, `stdout.txt` and `stderr.txt` are
  kept in `$SCREENDOOR_TRIAL_DIR` (`<run_dir>/trials/<trial_uuid>`). The
  script also gets `$SCREENDOOR_WORKDIR`, `$SCREENDOOR_ATTEMPT` and its
  `env`.
* A trial that exits 0 succeeds; its result is `null` unless the script
  sent one. A tagged line whose JSON does not parse is a `malformed` event
  in telemetry. The built-in assays count a null result as failed.
* `scd.churn.fold_trials` gives each trial a `task_id` (0, 1, 2, ... in
  request order), a `status` (`requested`, `killed`, `succeeded` or
  `failed`) and a `state`: `complete` once it has succeeded or failed,
  `pending` otherwise. It also
  carries `retries`, `kills` and `malformed` counts; the `closed` event and
  `print_status` tally them across trials, with `no_result` and
  `warnings`.

## Seeds

A dispatch has a `meta_seed`, an integer (32 random bits from the operating
system if absent at submit). `scd.churn.seed_global_rngs(assay)` wraps an
assay's churn so that each call first seeds `random` and, if installed,
`numpy.random` with `scd.churn.churn_seed(meta_seed, len(memo),
len(trial_submissions))`. In a recipe:

```json
"assay": "scd.churn.seed_global_rngs(scd.assaylib.testing.exercise)"
```

The rest of screendoor never touches a global RNG (the test suite checks
this), and trials get no seed unless churn puts one in their `env`. The
skeletonize assays' search keeps its own `random.Random(search_seed)`,
which defaults to `meta_seed`. Trial submissions and memos record their
`churn_step` (`"<memos>:<trial submissions>"`), which `replay_dispatch`
uses to re-run each churn call from the state it saw.

## Other notes

* `dispatch_payloads.jsonl` records `ticked` events; schedule due times
  and the consecutive-churn-error count are folded from them.
* A dispatch has five string labels beside its autogenerated
  `dispatch_uuid`: `meta_project`, `meta_experiment`, `meta_treatment`,
  `meta_user` and `meta_attempt`, each `"default"` if absent. They,
  `dispatch_uuid` and `meta_seed` are stamped on every record written for
  the dispatch and on `print_status --json` rows.
* Local daemons take an `flock` on the workdir, so starting two is
  harmless; Slurm daemon chains rely on `--dependency=singleton`.
* `submit_dispatch` only appends to `dispatch_submissions.jsonl`; start a
  daemon separately. For the Slurm chain, run `daemon.slurm.submit_daemon`
  after each submit or resume: it pulls a queued daemon job forward, or
  starts the chain if none is queued.
* `scd.auxlib` is public. Trial keys are dicts, so assays look folded
  trials up by `scd.auxlib.canonical_json(key)`:
  `by_key = {canonical_json(t["key"]): t for t in trials}`.
* `kill_dispatch [uuid...]` cancels unsettled trials through `how_kill`
  (`slurm.kill()` runs `scancel`; `subprocess.kill()` signals each batch's
  process group) and pauses the dispatch; `--slurm` also cancels the queued
  daemon job once nothing is active. A kill is not a result: the dispatch
  stays open and its trials show status `killed`. `resume_dispatch` lets
  the daemon tick it again; cancelled trials are relaunched without
  counting against `trial_maxretry`.
* `how_notify_liveness` and `how_notify_termination` are the daemon's own
  hooks, set in `screendoor.json`. Liveness is pinged once per daemon
  pass. Termination (default `scd.notify.log.notify()`) fires when the busy
  loop exits or the Slurm chain ends.
