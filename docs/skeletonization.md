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

Each policy reads in its own file (`ddmin/_churn.py`, `minesweeper/_churn.py`,
`hybrid/_churn.py`, where hybrid builds on ddmin's partition-union). The
machinery they share (evaluation, combination, audits and rollback, the final
sweep, and replaying a search as churn) is in `skeletonization/_knockout/`.

## How it maps onto churn

The search is written as a generator that yields each batch of genotypes to
evaluate. `churn` replays it from the start on every tick, feeding verdicts
computed from recorded trials, until it reaches a batch whose trials are not
all in. It launches those trials and returns. There is no memo: the trial
records are the state, so the search resumes exactly after any interruption,
and `replay_dispatch` re-checks every step.

Each trial key is `{"retained": "<sites as ranges>", "replicate": r}` (plus
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
| `combination_rounds` | 2 | Rounds of union proposals after accepted masks |
| `final_audit` | true | Re-test the skeleton afresh before certifying it |
| `audit_every` | 0 | Also audit after every this many commits (0: never) |
| `max_rollbacks` | 2 | Failed audits tolerated before giving up |
| `max_proposal_batches` | none | Stop (uncertified) after this many proposal batches |
| `initial_knockout_size` | none | Sites per initial ddmin chunk (default: halves) |
| `exact` | true | Exact-oracle mode, as in the original |
| `context_decay`, `memory_strength` | 4, 4 | Proposal memory's weighting of past acceptances |

Trials receive `env`, then `$retained`, `$knockout` (site ranges such as
`0-5,9`; decode with `scd.auxlib.decode_sites`), `$n_sites`, `$replicate`
and, with `sequence`, `$sequence`. A result is `true`/`false`, a number (the
score), an object with `accept`, or an object with `score` and optionally
`viable` and the `require_atleast` fields. A result of another shape, or
missing a field, fails the dispatch.

The dispatch succeeds whenever the search ends. Check `summary.certified`:
it is false if the search stopped early (`max_proposal_batches`, an audit
it could not resolve, or too many rollbacks), and `summary.status` says
why.

## Checked against the original

On Avida, `examples/avida/run_local.sh` (5 organisms, 3 policies, the daemon
SIGKILLed and restarted midway) retained the same sites as the original for
every organism and policy, and `test_matches_original_on_avida` checks this
in the test suite.

## Not ported

The noisy evaluators (`BernoulliEvaluator`, `ConcentrationEvaluator`:
anytime-valid confidence sequences and pooled Avida competitions) are not
ported. `replicates` averages a fixed number of trials and is not a
sequential test.
