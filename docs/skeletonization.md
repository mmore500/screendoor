# Knockout skeletonization assays

`scd.assaylib.skeletonization.{ddmin,minesweeper,hybrid,gama}` sample a
fitness-acceptable, single-deletion-minimal *skeleton* of a genome by
knocking out sites. The first three port the policies of the 2026-11-03
`knockout_skeleton` package (`search.py`, exact-oracle mode) to screendoor:

* **ddmin**: parallel partition-union delta debugging: disjoint chunk
  knockouts, union / partial-union repair of passing chunks, bisection of the
  survivors.
* **minesweeper**: exhaustive singleton screen, the 26 multi-scale Stage-2
  segments over the non-essential sites, Stage-3 combination, then Stage-4
  recursive 8-group divide and conquer.
* **hybrid**: one multi-dose pilot batch (50/25/12.5% doses); then top-down
  ddmin with pivots to a bottom-up singleton sieve and subspace reduction.

**gama** is new here: the Guess/Add/Mate genetic algorithm of Rees-Garbutt
et al. (2020) (see [GAMA](#gama) below).

All four finish with a complete singleton sweep and a fresh final audit, as
in the original. Every committed deletion was tested directly against the
fixed wildtype reference.

Each policy reads in its own file (`ddmin/_churn.py`, `minesweeper/_churn.py`,
`hybrid/_churn.py`, where hybrid builds on ddmin's partition-union, and
`gama/_churn.py`). The machinery they share (evaluation, combination, audits
and rollback, the final sweep, and replaying a search as churn) is in
`skeletonization/_knockout/`.

## How it maps onto churn

The search is written as a generator that yields each batch of genotypes to
evaluate. `churn` replays it from the start on every tick, feeding verdicts
computed from recorded trials, until it reaches a batch whose trials are not
all in. It launches those trials and returns. There is no memo: the trial
records are the state, so the search resumes exactly after any interruption,
and `replay_dispatch` re-checks every step.

Each trial key is `{"retained": "<sites as ranges>", "replicate": r}` (plus
`"fresh": n` for audits), so a genotype is never evaluated twice. The
wildtype's control trials are launched along with the first batch.

## The assay and its controls

Each policy module has a factory, `make_churn(*, num_control_trials=40)`,
and a `churn` made with the default, so either form works as an assay:

```json
"assay": "scd.assaylib.skeletonization.hybrid"
"assay": "scd.churn.seed_global_rngs(scd.assaylib.skeletonization.hybrid.make_churn(num_control_trials=40))"
```

The wildtype runs `num_control_trials` times (replicates 0 to n-1). These
control trials measure the wildtype against itself, for example as a
wildtype-vs-wildtype competition or as a Test CPU score less the
wildtype's own. Each candidate genotype runs `replicates` times, measured
against the wildtype the same way, and its scores are judged against the
controls' distribution by `control_test`:

* `t` (the default with 2 or more controls) is a one-sided t prediction
  bound. A candidate is rejected if its mean is below
  `limit - t(1 - alpha, n - 1) * sd * sqrt(1/n + 1/replicates)`, where
  `limit` is the controls' mean less the tolerance:
  `mean * (1 - rel_tol) - abs_tol`. This assumes a candidate's noise is
  the controls'.
* `rank` is a one-sided exact Mann-Whitney (rank-sum) test of the
  candidate's replicates, shifted up by the tolerance, against the
  controls. A candidate is rejected if p <= `alpha`. It makes no
  assumption about the distribution's shape, but its p-values are coarse:
  with 40 controls and 1 replicate, the smallest is 1/41 = 0.024. A
  setting whose smallest p-value is above `alpha` is refused.
* `mean` (the default with 1 control) accepts if the candidate's mean is
  at least `limit`. This is the rule from before there were controls.

If every control gives the same score, as Avida's deterministic Test CPU
does, the standard deviation is 0 and all three tests reject any score
below it, by more than 1e-12, unless a tolerance allows it.

The summary's `control` gives the test, the number of controls, their mean
and sd, `alpha`, and the `threshold` for `t` and `mean` (for `rank`, the
`smallest_pvalue` instead). Results of the `{"accept": bool}` kind are
judged by `accept_fraction` alone, and the controls are only run.

### Search and sweep rules

A dispatch runs in two phases, the policy's own search and then the sweep
(the singleton sweep and the final audit), and each phase has a rule:
`search_rule` and `sweep_rule`. Each rule is one of:

* `detectable_loss` (the default for both): a deletion is accepted unless
  its scores are clearly below the limit. This is the rule above.
* `noninferiority`: a deletion is accepted only when its loss is *shown*
  to be under the margin, `mean * rel_tol + abs_tol`. The margin must
  then be positive, unless the controls are identical.

`"sweep_rule": null` skips the sweep. With `final_audit`, the search's
result is still audited, by `search_rule`, and then returned uncertified,
with status `sweep_skipped`. ddmin and hybrid stop splitting at chunks of
two and leave the rest to the sweep, so without it they can keep sites
that a single deletion would remove.

**Screen, then confirm.** If either rule is `noninferiority`, every
genotype goes through two stages:

1. **Screen.** Replicate 0 alone is tested for a detectable loss at
   `screen_alpha`. A clearly harmful deletion is rejected after one trial.
2. **Confirm.** Replicates 1 to `replicates` run next, and are judged by
   the phase's rule at `alpha`. For `t`, `noninferiority` accepts a mean
   of at least `limit + t(1 - alpha, n - 1) * sd * sqrt(1/n +
   1/replicates)`, and `detectable_loss` one of at least `limit - ...` of
   the same. For `rank`, the replicates are shifted up by the margin;
   `noninferiority` needs them to rank significantly above the controls,
   and `detectable_loss` rejects them only if they rank significantly
   below. The screening replicate is left out of the confirmation. Only
   genotypes whose first draw looked good get this far, so counting it
   would bias the mean up.

The intended combination is `"search_rule": "noninferiority"` with the
default `"sweep_rule": "detectable_loss"`. Every deletion the search
commits is shown to cost less than the margin, and the sweep then removes
any remaining site whose loss is not detectable. When the rule changes at
the sweep, the search forgets its verdicts. They are judged again by the
sweep's rule from the trials already recorded, at no extra trial cost.
The reverse combination, a `detectable_loss` search with a
`noninferiority` sweep, holds the final skeleton to noninferiority
instead: a skeleton that fails the final audit is rolled back.

A screened candidate costs 1 trial if it is clearly harmful and
`1 + replicates` otherwise. The summary's `control` gives the `margin`,
whether there was a `sweep`, and the `stages`: `screen`, `search` and
`sweep`, each with its rule, alpha, replicates and threshold. For `t`,
each stage also gives its `harmless_pass_rate`, the chance that a deletion
with no effect passes it. `verdicts` counts each phase's verdicts, as
`search_screen_reject`, `search_noninferiority_accept`,
`sweep_detectable_loss_reject` and so on. For a harmless deletion to pass
`noninferiority` about 90% of the time with 40 controls at alpha 0.05,
the margin must be about 3 times the standard error,
`sd * sqrt(1/40 + 1/replicates)`:

| Margin / control sd | `replicates` |
|---|---|
| 3 | 1 to 2 |
| 2 | 3 |
| 1 | 12 |
| 0.5 | about 300 |
| under 0.47 | none suffice; add controls |

Screening needs scores; `{"accept": bool}` results are refused. With
identical controls there is no noise, and every rule accepts just a mean
of at least the limit, so any loss beyond the tolerance is a loss.

Every candidate is measured against the wildtype as a whole, not against
the genome it was proposed from, so small losses do not add up from step
to step: a skeleton is accepted only if it passes against the controls
itself. Each test has its own false-alarm rate, `alpha`, so with
thousands of tests about that fraction of harmless deletions are wrongly
kept, and the skeleton comes out somewhat larger than the true minimum.
A loss smaller than about the t margin above usually goes unnoticed.
More controls or `replicates` shrink that margin and make room for a
lower `alpha`.

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
| `replicates` | 1 | Trials per genotype; scores are averaged. With a `noninferiority` rule, the confirmation's trials, after the screen's one |
| `rel_tol`, `abs_tol` | 0, 0 | Accept if `score >= base*(1-rel_tol) - abs_tol` |
| `require_atleast` | `[]` | Result list fields that must not drop below wildtype (e.g. `tasks`) |
| `accept_fraction` | 1.0 | For `{"accept": bool}` results: fraction of replicates needed |
| `control_test` | `t` (`mean` with 1 control) | `t`, `rank` or `mean`: how scores are judged against the controls |
| `alpha` | 0.05 | One-sided false-alarm rate for `t` and `rank` |
| `search_rule` | `detectable_loss` | The search's rule: `detectable_loss` or `noninferiority` (see above) |
| `sweep_rule` | `detectable_loss` | The sweep's rule, or `null` for no sweep (uncertified, status `sweep_skipped`) |
| `screen_alpha` | `alpha` | With a `noninferiority` rule, the screen's alpha for a detectable loss on one replicate |
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
and, with `sequence`, `$sequence` and `$wildtype`, the unmasked sequence,
for example to compete against. A result is `true`/`false`, a number (the
score), an object with `accept`, or an object with `score` and optionally
`viable` and the `require_atleast` fields. A trial with no result (it
failed, or sent no `payload`), or a result of another shape or missing a
field, makes churn raise, and so fails the dispatch after
`churn_maxretry` retries.

The dispatch succeeds whenever the search ends. Check `summary.certified`:
it is false if the search stopped early (`max_proposal_batches`, an audit
it could not resolve, or too many rollbacks), and `summary.status` says
why.

## GAMA

Rees-Garbutt et al. 2020, "Designing minimal genomes using whole-cell
models", *Nat. Commun.* 11:836. Where the paper leaves a detail open, the
authors' code (GriersonMarucciLab/GAMA and whole_cell_modelling_suite)
settles it.

1. **Screen.** Knock out each site alone. The sites whose loss is
   acceptable are the *candidates*.
2. **Guess.** Split the candidates into `guess_sets` consecutive sets
   (four of about 40 genes in the paper). For each set, draw
   `guess_subsets` random deletions of 50 to 100% of the set, with the
   size drawn evenly from that range. The viable ones go forward.
3. **Add.** `add_combinations` times, pick 2 to all of the sets that have
   a viable guess, and one viable guess from each, and take their union.
4. **Mate.** Each generation has `mate_children` children. A child's
   parents are two of the `elite_size` largest viable deletions so far,
   drawn in proportion to their sizes (the authors' code; the paper says
   "at random"). The child inherits a random number of sites, picked at
   random, from the first parent and the rest from the second. With
   `mutation_probability`, it then flips a random number of sites
   anywhere in the genome, knocking them out or back in. That number is
   about exponential with mean `mutation_mean`, and at least one. A site
   that is essential on its own can go this way, as in the paper. The
   elite is updated after every generation. Mate stops after
   `mate_generations` generations, or after `mate_patience` in a row that
   find no larger deletion. The paper's run was stopped by hand under
   that rule, after 46 generations.
5. The largest viable deletion is committed. The common singleton sweep
   and audit then make it single-deletion minimal and certify it.
   The paper stops at step 4 and then hand-picks knock-ins to raise the
   division rate; `"sweep_rule": null` stops there too.

Every guess, union and child is tested against the wildtype, not against
the current genome, and only genotypes that have not been tested yet are
sent. `batch_size` therefore sets only how many go per wave: it changes
neither which deletions are tried nor the result. On a cluster, set it to
about one generation (the paper used 1000). Each churn call replays the
whole search, which stays cheap: about 0.4 s for 3,750 trials.

| Key | Default | Meaning |
|---|---|---|
| `guess_sets` | 4 | Sets the candidates are split into |
| `guess_subsets` | 400 | Random deletions drawn per set |
| `guess_min_fraction` | 0.5 | Smallest guess, as a fraction of its set (the authors' runs used about 0.7) |
| `add_combinations` | 3000 | Unions of viable guesses |
| `elite_size` | 50 | Largest viable deletions kept as parents |
| `mate_children` | 1000 | Children per generation |
| `mate_generations` | 100 | Most generations |
| `mate_patience` | 20 | Generations in a row without a larger deletion before stopping (`null`: never) |
| `mutation_probability` | 0.4 | Chance a child is mutated (the authors' GAMA scripts; their library default is 0.1) |
| `mutation_mean` | 2 | Mean number of sites a mutation flips |

These defaults are the paper's, which is about 10,000 to 40,000 trials even
on a 50 to 120 site toy landscape. For tests, or for genomes the other
policies can handle, much smaller numbers work: the Avida test uses 16
guesses, 32 unions, an elite of 8, 24 children and a patience of 3. The
summary's `stats` gives the candidates, viable guesses per set, viable
unions, generations run, and the largest deletion after each stage
(`deleted`).

The paper runs on the stochastic *M. genitalium* whole-cell model. Here,
use `replicates` with `accept_fraction` to get the same kind of verdicts.

## Minesweeper and the paper

`minesweeper` ports the 2026-11-03 policy exactly, and that policy is a
budgeted version of the paper's Minesweeper:

* Stage 2's 26 segments are made the same way as in the paper. Sizes are
  rounded rather than truncated, and the 50/33/25/12.5% segments are even
  splits. The authors' script used uneven chunks of `trunc(p*m)+1` sites,
  so their last 12.5% segment can come out empty.
* Stage 3 commits the 100% segment if it passes. Otherwise it runs up to
  `combination_rounds` batches of union proposals over the passing
  segments, where the paper simulates the whole powerset of the largest
  segment with every passing segment it does not overlap. It also follows
  one variant, where the paper follows three (red, yellow, blue).
* Stage 4 tests each of the 8 groups alone and combines the ones that
  pass. The paper appends each of the 255 nonempty unions of the groups.
  The paper's fallback, appending remaining genes one at a time and
  leaving out the ones that fail, is replaced by the common singleton
  sweep.
* Stage 1 screens every site; the paper skipped RNA genes.

On 24 synthetic landscapes (`essential`, `redundancy`, `mixed`, `rescue`;
50 and 120 sites; 3 seeds), the port was compared with a paper-exact,
single-variant Minesweeper written for the comparison and not shipped
here. They reached the same skeleton size on the 18
landscapes without a rescue pair. On each of the 6 `rescue` landscapes, the
paper-exact version stopped one site short of single-deletion minimal,
because it only deletes sites that pass the stage-1 screen. The port's
final sweep removed that site. Across all 24, the paper-exact version used
about 4 times as many trials (24,226 against 5,944 at `batch_size` 8).

## Checked against the original

On Avida, `examples/avida/run_local.sh` (5 organisms, 3 policies, the daemon
SIGKILLed and restarted midway) retained the same sites as the original for
every organism and policy, and `test_matches_original_on_avida` checks this
in the test suite. GAMA has no counterpart in the original.
`test_gama_known_skeletons` checks that it finds the benchmark's minimal
skeletons for `default_heads_50` and `nand_50`, and it did so with two
search seeds each.

## Not ported

The noisy evaluators (`BernoulliEvaluator`, `ConcentrationEvaluator`:
anytime-valid confidence sequences and pooled Avida competitions) are not
ported. `replicates` averages a fixed number of trials and is not a
sequential test.
