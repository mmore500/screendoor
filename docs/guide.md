# screendoor guide

How to write assays, configure dispatches and hooks, and run the daemon.
See the [README](../README.md) to get started.

## Writing an assay

An assay is a churn function, or a module with one:

```python
def churn(dispatch, trial_submissions, trial_payloads, memo) -> list:
    trials = scd.churn.fold_trials(trial_submissions, trial_payloads)
    ...
```

It gets the dispatch record (with `assay_kwargs`), the raw trial records,
and its memos, oldest first, and returns a list of actions. It is called
when `how_unblock_churn` lets it (`scd.unblock.all_trials_ready()`: once
no trial is outstanding), and again in the same tick after each memo. If
churn raises, the daemon retries it on later ticks, up to `churn_maxretry`
times in a row, then fails the dispatch with the error as its reason.

`fold_trials` gives one dict per trial: `trial_uuid`, `task_id` (0, 1, 2,
... in request order), `key`, `request`, `status` (`requested`, `killed`,
`succeeded` or `failed`), `state` (`complete` once succeeded or failed,
else `pending`), `attempt`, `job`, `result`, `channels`, `exit_code`
(`null` until it ends, or if its job was lost), and `retries` and `kills`
counts. Keys are dicts, so look trials up by
`scd.auxlib.canonical_json(key)`. Read results with
`scd.churn.trial_result(trial)`, which raises `RuntimeError` for a trial
with none: one that failed, or sent no `payload`.

| Action | Effect |
|---|---|
| `scd.churn.launch([{"key", "cmd", "env"}, ...])` | submit trials; a key already submitted is dropped |
| `scd.churn.memo(data)` | record state for the next call |
| `scd.churn.succeed(summary)`, `fail(reason)` | complete the dispatch |
| `scd.churn.progress(done, total, message=None)`, `eta(when)` | notify |
| `scd.churn.warning(message, *, dedupe_key=None, data=None)`, `anomaly(...)` | notify |

`env` values are strings; names starting `SCREENDOOR_` are reserved.

**Seeds.** A dispatch's `meta_seed` is an integer, 32 random bits from
the operating system if absent at submit. Wrap an assay as
`scd.churn.seed_global_rngs(assay)` to seed `random` and, if installed,
`numpy.random` before each call from `meta_seed`, `len(memo)` and
`len(trial_submissions)`. Nothing else in screendoor touches a global RNG,
and trials get no seed unless churn puts one in their `env`. Trial
submissions and memos record their `churn_step`, which `replay_dispatch`
uses to re-run each churn call from the state it saw.

## Built-in assays

| Assay | What it does |
|---|---|
| `scd.assaylib.testing.exercise` | `n` copies of `cmd`; succeeds with what they sent |
| `scd.assaylib.potentiation.naive_scan` | Replays from each of `timepoints` in turn, up to the first from which one succeeds |
| `scd.assaylib.skeletonization.jenga` | Removes `components` one per round, keeping those whose removal fails |
| `scd.assaylib.skeletonization.ddmin` | Parallel partition-union delta debugging |
| `scd.assaylib.skeletonization.minesweeper` | 4-stage Minesweeper (Rees-Garbutt 2020) |
| `scd.assaylib.skeletonization.hybrid` | Multi-dose pilot, then top-down ddmin or bottom-up sieve |
| `scd.assaylib.skeletonization.gama` | Guess/Add/Mate genetic algorithm (Rees-Garbutt 2020) |
| `scd.assaylib.skeletonization.staged` | Cheap screens for lethal knockouts, a regression ranking, then one confirmed cutoff |

Each skeletonization module also has `make_churn(*,
num_control_trials=40)`. The wildtype runs that many times as controls,
and candidate scores are judged against their distribution by a t
prediction bound or a rank test. `search_rule` and `sweep_rule` choose,
for the search and for the final sweep, whether a deletion must show no
detectable loss or be shown noninferior; `"sweep_rule": null` skips the
sweep. The `sprt` and `mixture` rules show noninferiority sequentially,
running more trials only for the genotypes that need them.

Each assay's docstring lists its kwargs (for the skeletonization
strategies, see docs/skeletonization.md). Pass/fail results are `true` or
`{"accept": true}` (`scd.assaylib.accepted`); a trial with no result makes
churn raise. The user's `env` goes to every trial, under the assay's own
variables. See
[skeletonization.md](skeletonization.md), and
[examples/avida](../examples/avida) for running the skeletonization assays on
Avida.

## Dispatches

| Setting | Default | |
|---|---|---|
| `assay`, `schedule` | required | an assay expression; a five-field cron schedule |
| `assay_kwargs` | `{}` | |
| `meta_project`, `meta_experiment`, `meta_treatment`, `meta_user` | `"default"` | labels |
| `meta_redo` | `"0"` | label; bump it to run the same labels again |
| `meta_seed` | random | integer |
| `trial_batchsize` | 1 | trials per job (array task) |
| `trial_batch_timeout` | none | seconds per job, enforced by the orchestrator |
| `trial_maxretry` | 3 | relaunches of a trial whose job vanished |
| `churn_maxretry` | 5 | retries of a churn call that raised, before the dispatch fails |
| `eval_context` | `import importlib; import logging; import screendoor as scd` | statements that make the namespace hooks are evaluated in |
| `dispatch_uuid` | random | |

The labels, `dispatch_uuid` and `meta_seed` are stamped on every record.
A dispatch runs in `<dispatchdir>/project=<project>/date=<YYYY-MM-DD>+what=
<experiment>%<treatment>%<seed>+redo=<redo>/`; setup deletes whatever an
earlier dispatch left there, and submit refuses a dispatch whose run
directory an open one is using.

Hooks, and the assay, are expressions, evaluated in the namespace that
`eval_context` makes; submit evaluates each and refuses a dispatch if one
raises. screendoor's own hooks are factories that take keyword arguments
only, such as `scd.orch.slurm.throttle(max_jobs=500)`. A dispatch sets
every name in `scd.auxlib.HOOK_NAMES`; `dispatch_hooks.json` sets every name
in `scd.auxlib.DISPATCHDIR_HOOK_NAMES`. Each hook's first argument,
`ctx`, is a dict: `{"dispatchdir", "run_dir", "dispatch_uuid",
"dispatch"}` for a dispatch's hooks, the last its record, and
`{"dispatchdir"}` for `dispatch_hooks.json` hooks (except `how_log_info`,
which gets only a message).

| Hook | Called as |
|---|---|
| `how_launch` | `(ctx, name, batches)`: start job `name`, batch `i` (a list of `{trial_uuid, attempt}`) as task `i` |
| `how_poke` | `(ctx, trials) -> {trial_uuid}`: the trials whose job is gone |
| `how_kill` | `(ctx, trials)`: cancel the trials' jobs |
| `how_throttle_churn` | `(ctx) -> bool`: false keeps churn from launching or memoing |
| `how_unblock_churn` | `(ctx, trial_submissions, trial_payloads) -> bool` |
| `how_setup` | `(ctx)`: prepare storage, once per dispatch |
| `how_prep_trial_payloads` | `(ctx, n_trials)`: make room before a launch |
| `how_read_<file>`, `how_write_<file>` | `(ctx)` and `(ctx, record)`, per record file |
| `how_cleanup_success`, `how_cleanup_failure` | `(ctx, completed)` once the dispatch completes |
| `how_notify_<level>` | see `scd.notify` |

## Trials

The worker (`python3 -m screendoor.trial.worker --dispatchdir D --dispatch
U <trial_uuid>...`) runs each trial's `cmd` with bash in a fresh temporary
directory, deleted afterwards. `cmd.sh` and `attempt-<n>/stdout.txt` and
`stderr.txt` stay in `$SCREENDOOR_TRIAL_DIR`. The script also gets
`$SCREENDOOR_DISPATCHDIR`, `$SCREENDOOR_ATTEMPT` and its `env`.

A script reports by printing `!!!screendoor:<channel> <json>` lines:
`payload` sets its result (the last one wins); `telemetry` values are also
recorded as they come; any other channel is collected into `channels`.
Lines whose JSON does not parse are skipped, with a warning in the job's
log. A trial that exits 0 succeeds, with the result it sent (`null` if
none); one that exits nonzero fails, with no result.

## Running the daemon

Run it as a busy loop (`run_busyloop`), from cron (`run_tick_once`), or as
a self-requeueing Slurm chain (`daemon.slurm.submit_daemon`, after each
submit or resume). Local daemons take an `flock` on the dispatchdir, so
starting two is harmless. Each Slurm daemon job queues its successor
before ticking, timed by `--begin` for when a dispatch is next due.

Each tick of an open dispatch:

1. polls each unsettled trial's job, and relaunches those that are gone,
   or records them `failed` (lost) after `trial_maxretry` relaunches;
2. calls churn, if unblocked, and carries out its actions;
3. on `succeed` or `fail`, records `completed` and calls the cleanup hook.

Before launching, the daemon records each trial's job (`job: {name,
index}`) in its submission, so poke can find it from the records alone
after a crash; a crash between recording and launching costs one relaunch.
A crash after `completed` is recorded skips that dispatch's cleanup and
final notification.

`kill_dispatch [uuid-prefix...]` cancels unsettled trials and pauses the
dispatch; `resume_dispatch` lets it run again, relaunching the cancelled
trials without counting a retry. `replay_dispatch <run_dir>` re-runs churn
at every recorded step and reports whether it decides the same.

## Storage

| File | Holds |
|---|---|
| `dispatch_submissions.jsonl` | `submitted`: one per dispatch |
| `dispatch_payloads.jsonl` | `completed`: how each dispatch ended |
| `dispatch_telemetry.jsonl` | `setup`, `ticked`, `churn_error`, `cleanup_error`, `killed`, `resumed` |
| `dispatch_notify.jsonl`, `dispatch_log.txt` | the daemon's own notices and log |
| `<run_dir>/trial_submissions.jsonl` | `requested` (one per attempt), `killed` |
| `<run_dir>/trial_payloads.jsonl` | `completed`, `failed` |
| `<run_dir>/trial_telemetry.jsonl` | `started`, `telemetry` |
| `<run_dir>/churn_memo.jsonl`, `churn_notify.jsonl` | memos, notifications |

Two backends provide the record hooks:

* `scd.record.appendjsonl`: one `O_APPEND` write per line. With
  `lock=True`, reads and writes hold `fcntl` locks, for filesystems where
  `O_APPEND` can tear lines (NFS across nodes); `timeout=` bounds the wait
  for a lock, in seconds.
* `scd.record.slottedjsonl`: trial payloads only, each in a fixed-size,
  checksummed slot of `trial_payloads.slots.jsonl`, lock-free. Set the slot
  size once, as `prep_trial_payloads(slot_bytes=...)` (default 32768); a
  payload too large for its slot is appended instead.

## Orchestrators

`scd.orch.subprocess` runs each batch as a detached local process;
`scd.orch.slurm` submits each job as one `sbatch --array` and polls with
one `squeue` per tick; `scd.orch.inline` runs trials in the daemon's
process, for tests. Each has `launch`, `poke`, `kill` and `throttle`.

## Development

```bash
python3 -m pytest            # Avida tests run when an avida binary is found
python3 scripts/bare_exercise.py
./scripts/build_pyz.sh       # single-file dist/screendoor-<v>.pyz
```

`scd.testing.simulate_dispatch` runs a dispatch in fake time with
`scd.testing.INLINE_HOOKS` and `DISPATCHDIR_HOOKS`, complete hook sets on
the inline orchestrator.
