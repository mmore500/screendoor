# Knockout skeletonization assays

`scd.assaylib.skeletonization.{ddmin,minesweeper,hybrid}` sample a
fitness-acceptable, single-deletion-minimal *skeleton* of a genome by
knocking out sites. They port the policies of the 2026-11-03
`knockout_skeleton` package (`search.py`, exact-oracle mode) to screendoor:

* **ddmin**: parallel partition-union delta debugging: disjoint chunk
  knockouts, union / partial-union repair of passing chunks, bisection of the
  survivors.
* **minesweeper**: exhaustive singleton screen, the 26 multi-scale Stage-2
  segments over the non-essential sites, Stage-3 combination, then Stage-4
  recursive 8-group divide and conquer.
* **hybrid**: one multi-dose pilot batch (50/25/12.5% doses); then top-down
  ddmin with pivots to a bottom-up singleton sieve and subspace reduction.

All three finish with a complete singleton sweep and a fresh final audit, as
in the original. Every committed deletion was tested directly against the
fixed wildtype reference.

## How it maps onto churn

The search is written as a generator that yields each batch of genotypes to
evaluate. `churn` replays it from the start on every tick, feeding verdicts
computed from recorded trials, until it reaches a batch whose trials are not
all in. It launches those trials and returns. There is no memo: the trial
records are the state, so the search resumes exactly after any interruption,
and `replay_dispatch` re-checks every step.

Each trial key is `{"g": "<retained sites as ranges>", "rep": r}` (plus
`"fresh": n` for audits), so a genotype is never evaluated twice. The
wildtype reference is launched along with the first batch.

Given the same `search_seed`, `batch_size` and verdicts, the port takes the
same path as the original: the same skeleton, proposal batches and
certificate (checked by `test_matches_2026_11_03_implementation` and
`test_matches_original_on_avida`).

## assay_kwargs

| Key | Default | Meaning |
|---|---|---|
| `n_sites` or `sequence` | required | Genome size, or the wildtype sequence |
| `nop_symbol` | `"A"` | Replaces knocked-out sites in `$sequence` |
| `cmd` | required | Trial script |
| `env` | `{}` | Extra trial environment |
| `batch_size` | 8 | Candidates per wave (the original's `max_parallel`) |
| `replicates` | 1 | Trials per genotype; scores are averaged |
| `rel_tol`, `abs_tol` | 0, 0 | Accept if `score >= base*(1-rel_tol) - abs_tol` |
| `require_atleast` | `[]` | Result list fields that must not drop below wildtype (e.g. `tasks`) |
| `accept_fraction` | 1.0 | For `{"accept": bool}` results: fraction of replicates needed |
| `on_trial_failure` | `"fail"` | `"fail"` the dispatch, or `"reject"` the genotype |
| `search_seed` | the dispatch's `meta_seed` | Seed of the search's own RNG |
| `combination_rounds`, `final_audit`, `audit_every`, `max_rollbacks`, `max_proposal_batches`, `initial_knockout_size`, `exact` | as in `SearchConfig` | |

Trials receive `$retained`, `$knockout` (site ranges such as `0-5,9`),
`$n_sites`, `$replicate` and, with `sequence`, `$sequence`. A result is
`true`/`false`, a number (the score), or an object with `accept`, or with
`score` and optionally `viable` and the `require_atleast` fields.

## Local Avida end-to-end run

`examples/avida/run_local.sh` sent 15 dispatches (5 organisms × 3 policies,
`search_seed` 42, batch 8) through the cron daemon and the subprocess
orchestrator. The daemon was SIGKILLed at 330 s and restarted. All 15
succeeded with no trial retries, all certified, and every retained set
matched `knockout_skeleton` from 2026-11-03.

| organism | policy | retained | batches | trials |
|---|---|---:|---:|---:|
| default_heads_50 | ddmin / minesweeper / hybrid | 15/50 | 10 / 10 / 9 | 62 / 75 / 59 |
| nand_50 | ddmin / minesweeper / hybrid | 20/50 | 16 / 11 / 15 | 101 / 80 / 103 |
| redundant_nand_50 | ddmin / minesweeper / hybrid | 20/50 | 19 / 19 / 13 | 131 / 129 / 99 |
| small_effect_vb_50 | ddmin / minesweeper / hybrid | 30/50 | 19 / 28 / 27 | 127 / 202 / 193 |
| evolved_9task_67 | ddmin / minesweeper / hybrid | 59/67 | 34 / 27 / 28 | 244 / 208 / 213 |

On redundant_nand_50 the three policies keep different copies of the
redundant NAND block. The counts match, and each one matches what the
original returns for the same policy.

## Not ported

The noisy evaluators (`BernoulliEvaluator`, `ConcentrationEvaluator`:
anytime-valid confidence sequences and pooled Avida competitions) are not
ported. `replicates` averages a fixed number of trials and is not a
sequential test.
