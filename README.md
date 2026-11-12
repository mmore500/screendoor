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
* **Every side effect is a hook** (`how_launch`, `how_poke`, `how_throttle_churn`,
  `how_unblock_churn`, `how_cleanup_*`, `how_notify_*`,
  `how_read_*`/`how_write_*`), and none has a default: a dispatch must set
  all of its hooks, and the workdir's `screendoor.json` all of the
  daemon's.
* **Trials are shell scripts** that print `!!!screendoor:payload <json>`.
* **Standard library only**, Python 3.10+. No database, broker or server.
* **screendoor never kills anything.** Timeouts belong to the orchestrator.

## Quick start

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
    echo "!!!screendoor:payload \$((i * i))"
schedule: "* * * * *"
how_launch: scd.orch.subprocess.launch()
how_poke: scd.orch.subprocess.poke()
how_kill: scd.orch.subprocess.kill()
how_throttle_churn: scd.orch.subprocess.throttle(max_procs=4)
how_setup: scd.record.appendjsonl.setup()
how_read_trial_submissions: scd.record.appendjsonl.read_trial_submissions()
how_write_trial_submissions: scd.record.appendjsonl.write_trial_submissions()
how_read_trial_payloads: scd.record.appendjsonl.read_trial_payloads()
how_write_trial_payloads: scd.record.appendjsonl.write_trial_payloads()
how_prep_trial_payloads: scd.record.appendjsonl.prep_trial_payloads()
how_read_trial_telemetry: scd.record.appendjsonl.read_trial_telemetry()
how_write_trial_telemetry: scd.record.appendjsonl.write_trial_telemetry()
how_read_memo: scd.record.appendjsonl.read_memo()
how_write_memo: scd.record.appendjsonl.write_memo()
how_read_notify: scd.record.appendjsonl.read_notify()
how_write_notify: scd.record.appendjsonl.write_notify()
how_notify_progress: scd.notify.log.notify()
how_notify_eta: scd.notify.log.notify()
how_notify_success: scd.notify.log.notify()
how_notify_failure: scd.notify.log.notify()
how_notify_warning: scd.notify.log.notify()
how_notify_anomaly: scd.notify.log.notify()
how_unblock_churn: scd.unblock.all_trials_ready
how_cleanup_success: "lambda *args, **kwargs: (scd.cleanup.tar(*args, **kwargs), scd.cleanup.clear(*args, **kwargs))"
how_cleanup_failure: "lambda *args, **kwargs: None"
YAML
python3 -m screendoor.daemon.run_busyloop --workdir work
python3 -m screendoor.daemon.print_status --workdir work
```

What each part does:

* **`screendoor.json`** holds the daemon's own hooks: where dispatch
  records live, how it logs, and its liveness and termination notices.
  Every command on the workdir reads it.
* **The dispatch** has labels (`meta_*`; `meta_seed` seeds churn), the
  assay and its kwargs, a cron `schedule`, and all of its hooks. The
  assay here is the smoke test: it launches `n` trials of `cmd`, each with
  `$i` in its env, and succeeds with what they sent. Wrapping it in
  `scd.churn.seed_global_rngs` seeds `random` (and numpy) before each
  churn call.
* **A trial** is `cmd` run by bash in a temporary directory; it reports
  its result by printing `!!!screendoor:payload <json>`.
* **`run_busyloop`** ticks until no dispatch is open: it launches the
  trials as local processes, waits for them (`how_unblock_churn`), calls
  churn again, and records the dispatch `completed`.

No hook has a default. Submitting a dispatch that leaves one out fails,
naming the missing ones; so does any command on a workdir whose
`screendoor.json` leaves one out. The heredoc delimiter is unquoted so
that the shell fills in `meta_user` and `meta_attempt`; in exchange, each
`$` meant for the trial script is written `\$`. Submitting only records
the dispatch: the daemon is started separately.

Afterwards `print_status` shows the dispatch `succeeded` with results
`[0, 1, 4, 9]`, and `work/` holds:

```
work/
  screendoor.json
  dispatch_submissions.jsonl   # the dispatch as submitted
  dispatch_payloads.jsonl      # `completed`: how it ended
  dispatch_telemetry.jsonl     # setup, ticks
  screendoor-log.txt           # the daemon's log
  screendoor-notify.jsonl      # its liveness and termination notices
  assay=exercise+date=...+uuid=...+what=screendoor/
    trial_submissions.jsonl    # one `requested` per trial attempt
    trial_payloads.jsonl       # each trial's result
    trial_telemetry.jsonl      # when and where each trial ran
    notify.jsonl
    jobs/                      # the local processes' pidfiles and logs
    trials.tar.gz              # trials/ (cmd.sh, stdout, stderr), archived
```

For tests, `scd.testing.INLINE_HOOKS` and `scd.testing.WORKDIR_HOOKS` are
complete hook sets on the inline orchestrator, and `simulate_dispatch`
supplies them.

`python3 -m screendoor` lists every command. Run the daemon as a busy loop
(`run_busyloop`), from cron (`run_tick_once`), or as a self-requeueing Slurm
chain (`daemon.slurm.submit_daemon`).

## Assays

| Assay | What it does |
|---|---|
| `scd.assaylib.testing.exercise` | Smoke test: n copies of a command |
| `scd.assaylib.potentiation.naive_scan` | Replays from each timepoint in turn, up to the first that succeeds |
| `scd.assaylib.skeletonization.naive_jenga` | One removal per round, memo-driven |
| `scd.assaylib.skeletonization.ddmin` | Parallel partition-union delta debugging |
| `scd.assaylib.skeletonization.minesweeper` | 4-stage Minesweeper (Rees-Garbutt 2020) |
| `scd.assaylib.skeletonization.hybrid` | Multi-dose pilot + top-down ddmin / bottom-up sieve |

The three knockout-skeletonization strategies come from the 2026-11-03
`knockout_skeleton` work. See [docs/skeletonization.md](docs/skeletonization.md),
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
| `dispatch_payloads.jsonl` | `completed`: how each dispatch ended, with its outcome | the daemon |
| `dispatch_telemetry.jsonl` | `setup`, `ticked`, `churn_error`, `cleanup_error`; `killed`, `resumed` | the daemon; `kill_dispatch`, `resume_dispatch` |
| `<run_dir>/trial_submissions.jsonl` | `requested` (one per attempt, naming its job), `killed` | the daemon |
| `<run_dir>/trial_payloads.jsonl` | `completed`, `failed`: results only | workers; the daemon for `failed: lost` |
| `<run_dir>/trial_telemetry.jsonl` | `started` (pid, host), `telemetry` values, `malformed` lines | workers |
| `<run_dir>/memo.jsonl`, `notify.jsonl` | memos, notifications | the daemon |

Each file has a `how_read_<file>` and `how_write_<file>` hook. The dispatch
hooks (`how_read_dispatch_submissions`, ...) are the daemon's own, set in
`<workdir>/screendoor.json`; the rest are per dispatch. Three storage
backends provide them:

* `scd.record.appendjsonl`: one `O_APPEND` write per line.
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
  multiple of 4096; default 32768); the other two hooks take it from the
  file, and raise `ValueError` if given a different one. A payload too
  large for its slot is appended to `trial_payloads.jsonl` instead.

`<workdir>/screendoor-notify.jsonl` (the daemon's liveness and termination
notices) is always appended directly.

## The daemon's pass

For each open dispatch, a tick:

1. polls every unsettled trial's job (`how_poke`), and relaunches those
   whose job is gone, or records them `failed: lost` after
   `trial_maxretry` relaunches;
2. checks `how_throttle_churn(ctx)`; when it is false, churn may still notify,
   succeed or fail, but not launch or memo;
3. calls `how_unblock_churn(ctx, trial_submissions, trial_payloads)`, and
   only if it is true, `churn`. `scd.unblock.all_trials_ready` waits
   until no submitted trial is outstanding. Churn is called again in the
   same tick after each memo.
4. on `succeed` or `fail`, records `completed` and calls
   `how_cleanup_success(ctx, completed)` or
   `how_cleanup_failure(ctx, completed)`. `scd.cleanup.tar` archives
   `trials/` to `trials.tar.gz` and `scd.cleanup.clear` deletes it; the
   recipes do both on success and nothing on failure. A cleanup that
   raises is recorded as `cleanup_error`.

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
* `how_throttle_churn(ctx) -> bool`: `lambda *args, **kwargs: True` never
  throttles.

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
  carries `retries`, `kills` and `malformed` counts; the `completed` event and
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
skeletonization assays' search keeps its own `random.Random(search_seed)`,
which defaults to `meta_seed`. Trial submissions and memos record their
`churn_step` (`"<memos>:<trial submissions>"`), which `replay_dispatch`
uses to re-run each churn call from the state it saw.

## Other notes

* `dispatch_telemetry.jsonl` records `ticked` events; schedule due times
  and the consecutive-churn-error count are folded from them.
* A dispatch has five string labels beside its autogenerated
  `dispatch_uuid`: `meta_project`, `meta_experiment`, `meta_treatment`,
  `meta_user` and `meta_attempt`, each `"default"` if absent. They,
  `dispatch_uuid` and `meta_seed` are stamped on every record written for
  the dispatch and on `print_status --json` rows.
* Local daemons take an `flock` on the workdir, so starting two is
  harmless. In a Slurm daemon chain, each job queues its successor
  before ticking, timed by `--begin` for when a dispatch is next due after
  that tick; jobs do not wait on each other's completion, and one that
  starts while another still ticks finds the lock held and skips its tick.
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
  pass. Termination fires when the busy loop exits or the Slurm chain
  ends.
