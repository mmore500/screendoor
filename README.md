# screendoor

screendoor runs *dynamic screens*: searches over trials (knockouts, ablations,
parameter sweeps) where the next trials depend on the results of earlier
ones. A daemon wakes on a cron schedule, rebuilds state from append-only JSONL
records, asks the assay's `churn` function what to do next, and carries out
the actions it returns.

* **The records are the state.** Kill the daemon at any moment; start it
  again and the dispatch resumes.
* **Assays are pure.** `churn(dispatch, trials, memo, *, rng) -> actions`.
* **Every side effect is a hook** (`how_launch`, `how_poke`, `how_throttle`,
  `how_notify_*`, `how_read_*`/`how_write_*`), each with a default.
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
assay: scd.assaylib.testing.exercise
assay_kwargs:
  n: 4
  cmd: |
    set -euo pipefail
    echo "!!!screendoor:result \$((i * i))"
schedule: "* * * * *"
how_launch: scd.orchestrate.subprocess.launch()
how_poke: scd.orchestrate.subprocess.poke()
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
`scd.orchestrate.slurm.launch(worker="python3 /shared/screendoor-0.1.0.pyz worker")`.

## Implementation notes beyond the design

* `screendoor-dispatch.jsonl` also records `ticked` events (schedule due
  times and the consecutive-churn-error count are folded from them).
* `requested` events carry the `launch_id`; `reconcile` groups unlaunched
  trials by it and asks the launcher's `adopt(ctx, launch_id, entries)` for
  jobs that exist already.
* Hook signatures: `how_launch(ctx, entries, launch_id) -> entries+job_id`,
  `how_poke(ctx, launched_trials) -> {trial_uuid gone}`,
  `how_throttle(ctx) -> bool`, notifiers as in the design.
* Worker CLI: `python3 -m screendoor.worker --workdir W --dispatch U
  <trial_uuid|trial_dir>...`. It also sets `SCREENDOOR_ATTEMPT`.
* Local daemons take an `flock` on the workdir, so starting two is harmless;
  Slurm daemon chains rely on `--dependency=singleton`.
* `submit_dispatch` only appends to `screendoor-dispatch.jsonl`; start a
  daemon separately. For the Slurm chain, run `daemon.slurm.submit_daemon`
  after each submit or resume: it pulls a queued daemon job forward, or
  starts the chain if none is queued.
* `scd.auxlib` is public. Trial keys are dicts, so assays look trials up
  by `scd.auxlib.canonical_json(key)`:
  `by_key = {canonical_json(t["key"]): t for t in trials}`.
* Seeds are 32-bit, not 128-bit: `derive_seed` keeps four bytes of the
  digest, so `$SCREENDOOR_SEED` fits the seed argument of nearly any program.
* `kill_dispatch [uuid...]` cancels in-progress trials through `how_kill`
  (`slurm.kill()` runs `scancel`; `subprocess.kill()` signals each batch's
  process group) and pauses the dispatch; `--slurm` also cancels the queued
  daemon job once nothing is active. A kill is not a result: the dispatch
  stays open, trials show status `killed`, and `killed` events go to
  `screendoor-dispatch.jsonl` and `payload.jsonl`. `resume_dispatch` lets the
  daemon tick it again; cancelled trials are relaunched without counting
  against `trial_maxretry`.
* A trial that exits 0 always succeeds; its result is `null` unless the
  script sent one, so `null` is not a result a script can usefully send and
  the `no_result` and `bad_json` failure kinds are gone. A tagged line whose
  JSON does not parse is recorded as a `malformed` event in
  `telemetry.jsonl`. The built-in assays count a null result as a failed
  trial.
* A dispatch has five labels beside its autogenerated `dispatch_uuid`:
  `meta_project`, `meta_experiment`, `meta_treatment`, `meta_user` and
  `meta_attempt`, each `"default"` if absent. All six are stamped on every
  record written for the dispatch, in `screendoor-dispatch.jsonl`,
  `payload.jsonl`, `memo.jsonl`, `notify.jsonl` and `telemetry.jsonl`, and on
  `print_status --json` rows.
* `how_notify_liveness` and `how_notify_termination` are the daemon's own
  hooks, set in `screendoor.json` beside `how_read_dispatch`,
  `how_write_dispatch` and `how_log_info`; a dispatch cannot set them.
  Liveness is pinged once per daemon pass. Termination (default
  `scd.notify.log.notify()`) fires when the busy loop exits or the Slurm
  chain ends. Their records go to `<workdir>/screendoor-notify.jsonl`.
* `scd.record.slottedjsonl` implements Slotted JSONL v0.1 (`init`,
  `extend`, `write`, `read`, `missing`, `convert`, `encode_slot`,
  `decode_slot`): one fixed-size, checksummed slot per record, so many
  writers can fill one shared file with no locks.
* Every trial has a `task_id`: 0, 1, 2, ... in request order. To have
  workers record trials lock-free, set `how_read_payload`, `how_write_payload`
  and `how_prep_payload` to `scd.record.slottedjsonl.read_payload()`,
  `write_payload()` and `prep_payload()`. Each worker's `started`,
  `completed` and `failed` events then go to line `task_id` of
  `payload.slots.jsonl`, the newest replacing the last; the daemon's own
  events are still appended to `payload.jsonl`. `how_prep_payload(ctx,
  n_trials)` is a new hook the daemon calls before every launch, so that
  the slots exist before their writers start; the default,
  `scd.record.jsonl.prep_payload()`, does nothing.
* The slot size is set once, on the hook that makes the file:
  `scd.record.slottedjsonl.prep_payload(slot_bytes=8192)` (a multiple of
  4096; default 4096). `read_payload()` and `write_payload()` take the size
  from the file, since each slot is one line. A `slot_bytes=` given to them
  that differs from the file's raises `ValueError`.
* `scd.record.lockedjsonl` is the same JSONL as `scd.record.jsonl`, but
  each append holds an exclusive `fcntl` lock on the file and each read a
  shared one. It is for filesystems where `O_APPEND` alone can tear or
  interleave lines, such as NFS shared across nodes. It has every
  `read_*`/`write_*` hook (payload, memo, notify, telemetry, and dispatch for
  `screendoor.json`), plus a no-op `prep_payload()`. Each takes
  `timeout=` (seconds, default: wait forever) and raises
  `LockTimeoutError` past it. Before appending, it ends any unterminated
  last line left by a writer that died mid-write, so the next record is
  not spliced onto it. `fcntl` locks belong to the process, so a
  per-path thread lock also keeps one process's threads apart.
  `screendoor-notify.jsonl` (the daemon's liveness and termination
  records) is still appended without a lock.
* Each trial has a `state` beside its `status`: `complete` once it has
  succeeded or failed, `pending` otherwise (requested, launched, running or
  killed). Assays wait on `state` and read the outcome from `status`.
* Trials carry `retries`, `kills` and `malformed` counts. The `closed` event
  and `print_status` carry a `tally` of them across trials, plus `no_result`
  (null results) and `warnings`: the number of values trials sent on the
  `warning` channel.
