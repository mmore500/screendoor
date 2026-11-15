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

A fifth assay, **staged**, works differently: it needs a cheap pass/fail
screen for large failures, and estimates small costs by regression (see
[Staged](#staged) below).

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
* `sprt` or `mixture`: noninferiority again, but judged sequentially,
  with an error rate for the whole search (see
  [Sequential rules](#sequential-rules) below).

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

### Sequential rules

`sprt` and `mixture` are noninferiority rules too, but they take a
genotype's trials a few at a time and stop as soon as its scores decide.
A clearly harmful deletion costs one trial, a clearly harmless one a
handful, and only deletions near the margin run long. They also bound the
chance of a wrong acceptance over the whole search, where `alpha` bounds
it for each test alone.

* `sprt` is Wald's sequential probability ratio test. It tests a loss of
  the whole margin against a loss smaller by the *indifference zone*,
  `indifference` of the margin (0.4 by default). It accepts once the
  likelihood ratio reaches `1 / alpha`, and gives up once it falls to
  `futility` (0.1), which rejects the deletion without showing that it
  loses more than the margin. A deletion that loses more than the margin
  less half the zone is usually given up; one that loses less is accepted
  in the end.
* `mixture` is the normal-mixture confidence sequence of Howard et al.
  (2021), tuned to the same zone. It accepts once the whole interval for
  the genotype's mean score is above the limit, and rejects once it is
  below, which does show a loss beyond the margin. It has no zone to give
  up in, so a deletion near the margin runs to `max_replicates`.

**Looks.** A genotype's first look takes `replicates` trials, and each
later look doubles the total, up to `max_replicates` (64). A genotype
still undecided there is rejected, and counted as `capped`. Scores are
judged in replicate order and the first verdict reached stands, so a
replay gives the same verdict whatever came in later.

**Error rate.** `error_rate` (0.05) bounds the chance that any test of
the whole search accepts a deletion that loses more than the margin. It
is spent in three parts:

* An eighth goes to an upper confidence bound on the wildtype's mean,
  which raises the limit by `t(1 - error_rate/8, n - 1) * sd / sqrt(n)`
  (times `1 - rel_tol`). The margin must be wider than that.
* An eighth goes to an upper confidence bound on the wildtype's standard
  deviation, `sd * sqrt((n - 1) / chi2(error_rate/8, n - 1))`, which every
  test takes as the noise.
* The rest is shared among the tests. The first `planned_tests` tests (8
  per site by default) share half of it evenly, the next twice as many
  share a quarter, and so on. A search never runs out, but tests past
  the plan need more trials each.

This assumes normal scores, with a candidate's no noisier than the
controls'. With 40 controls the two bounds are costly: the limit rises by
0.41 sd and the noise is taken as 1.38 sd. More controls make every test
cheaper. The stage's `harmless_replicates` in the summary is how many
scores at the controls' mean the first tests need to accept. For a
100-site genome at the defaults:

| Margin / control sd | `sprt`, 40 controls | `sprt`, 200 | `mixture`, 40 | `mixture`, 200 |
|---|---|---|---|---|
| 4 | 5 | 3 | 5 | 3 |
| 3 | 10 | 6 | 9 | 5 |
| 2 | 26 | 14 | 22 | 12 |
| 1.5 | 54 | 25 | 46 | 21 |
| 1 | 186 | 65 | 157 | 55 |

A setting whose `harmless_replicates` would exceed `max_replicates` is
refused, as no deletion could then be expected to pass.

**Combining rules.** A sequential rule goes in both phases, or with no
sweep, or with `detectable_loss` in the other phase. It cannot be mixed
with `noninferiority` or with the other sequential rule.

* With a sequential rule throughout, every commit has passed within the
  error rate, so the final audit is off unless `final_audit` is set. A
  fresh test of a skeleton near the margin would likely give up on it.
  The certificate then means that no single further deletion could be
  shown harmless within `max_replicates`.
* A `sprt` search with the default `detectable_loss` sweep commits only
  deletions shown harmless, then drops any remaining site whose loss is
  not detectable. The search's trials then start at replicate
  `replicates`, after the ones the sweep's rule judges.
* A `detectable_loss` search with a sequential sweep holds the final
  skeleton to the sequential rule by the final audit, as with
  `noninferiority`.

The stage's summary gives its `limit`, `sd_bound`, `indifference` zone
(in score units) and `max_replicates`, and `verdicts` counts
`search_sprt_accept`, `search_sprt_reject`, `search_sprt_capped` and so
on. Sequential rules need scores, and controls judged by `t`. With
identical controls there is no noise, and a genotype's first score
decides.

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
| `replicates` | 1 | Trials per genotype; scores are averaged. With a `noninferiority` rule, the confirmation's trials, after the screen's one. With a sequential rule, the first look's trials |
| `rel_tol`, `abs_tol` | 0, 0 | Accept if `score >= base*(1-rel_tol) - abs_tol` |
| `require_atleast` | `[]` | Result list fields that must not drop below wildtype (e.g. `tasks`) |
| `accept_fraction` | 1.0 | For `{"accept": bool}` results: fraction of replicates needed |
| `control_test` | `t` (`mean` with 1 control) | `t`, `rank` or `mean`: how scores are judged against the controls |
| `alpha` | 0.05 | One-sided false-alarm rate for `t` and `rank` |
| `search_rule` | `detectable_loss` | The search's rule: `detectable_loss`, `noninferiority`, `sprt` or `mixture` (see above) |
| `sweep_rule` | `detectable_loss` | The sweep's rule, or `null` for no sweep (uncertified, status `sweep_skipped`) |
| `screen_alpha` | `alpha` | With a `noninferiority` rule, the screen's alpha for a detectable loss on one replicate |
| `error_rate` | 0.05 | With a sequential rule, the chance that any test of the search accepts a loss beyond the margin |
| `indifference` | 0.4 | With a sequential rule, the indifference zone, as a fraction of the margin |
| `futility` | 0.1 | With `sprt`, the likelihood ratio at which a deletion is given up |
| `max_replicates` | 64 | With a sequential rule, the most trials per genotype |
| `planned_tests` | 8 per site | With a sequential rule, how many tests share the first half of the tests' error rate |
| `search_seed` | the dispatch's `meta_seed` | Seed of the search's own RNG |
| `combination_rounds` | 2 | Rounds of union proposals after accepted masks |
| `final_audit` | true (false with a sequential rule throughout) | Re-test the skeleton afresh before certifying it |
| `audit_every` | 0 | Also audit after every this many commits (0: never) |
| `audit_adaptive` | false | Audits pace themselves: one that passes doubles `audit_every`, one that fails halves it, finds the newest checkpoint that passes by bisection, and narrows the commit after it to a part that still fails, which is not deleted again. The result holds no commit unaudited. For a trial that tests an audit (`$fresh`) more strictly than the search |
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

## Staged

`scd.assaylib.skeletonization.staged` is for a genome where a cheap,
pass/fail *screen* can spot large failures, and only a long, scored trial
can measure small ones. It assumes **no rescue**: a knockout that fails
keeps failing with more sites out. It runs in three stages.

1. **Screens.** Random knockouts are screened at a dose that fails
   about half the time, and each failure is shrunk by bisection, several
   side by side, to a minimal failing set. A set of one is a critical
   site. A larger set is *jackknifed* (see below) to tell a redundant
   set, of which one member is kept and the rest go on, from losses
   adding up. The dose rises as sites are retained. The stage ends when
   the whole remaining pool, knocked out together, passes. A knockout
   the screen has settled is never asked for again: with no rescue, a
   knockout inside one that passed passes, and one containing a failing
   set fails.
2. **Ranking.** Score random knockouts of the pool with long trials, and
   estimate each site's cost by least squares on which sites were out.
   The trials double from 100 until `max_ranking_trials`, or until, with
   four trials a site or more, another deleted site is predicted to cost
   over `site_value` long trials. A site whose cost alone is clearly more
   than can be accepted is left in from then on.
3. **Confirmation.** Sort the pool from least to most costly and find,
   by bisection, the longest prefix whose knockout the
   [`sprt`](#sequential-rules) rule accepts against the wildtype
   controls. These few tests carry the whole `error_rate`. With
   `reconfirm`, a knockout the rule accepts is judged a second time, on
   the scores of a costlier trial (a larger or longer run, say) against
   controls scored the same way, and is accepted only if it passes both.
   The costlier test paces itself: the bisection is by the first
   confirmation, and the costlier one judges the longest prefix accepted
   so far after every `every` that the first accepts, and where the
   bisection ends, so that nothing is deleted that it has not accepted.
   A prefix it rejects becomes the bisection's upper bound. With `every`
   0 it judges only where the bisection ends: one costlier test where
   the two agree. With `adaptive`, each prefix it accepts doubles
   `every`, and each it rejects halves it.

**Redundant, or adding up?** A screen that detects a loss of some size
also fails when smaller losses add up to it, so a minimal failing set of
several sites is one of two things. If it is *redundant*, the genome is
fine until every member is out, and putting any one back leaves no loss.
If its losses *add up*, putting one back leaves most of the loss. The
jackknife puts each member back in turn and tests what is left with the
next test up: the next screen, which must be more sensitive, or, after
the last screen, `jackknife_replicates` long trials, which fail if their
mean loss is more than the confirmation could accept.

* If no leave-one-out knockout fails, the set is redundant, and one
  member is kept.
* If one fails, the losses add up. No member is kept for the set, and
  each member that fails the same test when knocked out alone is
  critical: a site that cannot be taken out alone is costly, and one
  that can is redundant or cheap, and stays in the pool.

Two leave-one-out knockouts are tested first, as they settle a set whose
losses add up: one of any two keeps at least half the set's loss. This
assumes that what the screen detects is over twice what the next test
does. A shrink gives up on a failing set of more than `max_set_size`
sites, which caps its cost; with a further screen, that knockout is then
searched by halving for sites harmful alone. Each later screen also
searches the whole pool by halving, and a kept member is released if
another member of its set turns out to be retained anyway.

**Trials.** A screen trial gets `$screen`, its number from 0 (the
cheapest), and passes if it sends `true` or `{"accept": true}`: the
knockout shows no large failure. A long trial gets no `$screen` and sends
a score, as a number or `{"score": ..., "viable": ...}`. A ranking sample
that is not viable is skipped and counted in `stats.nonviable`. Screens
run once each: a screen that misreads is not allowed for. A
reconfirmation's trials and its controls get `$reconfirm`, set to 1, and
the `env` and `cmd` of `reconfirm`.

| Key | Default | Meaning |
|---|---|---|
| `n_sites` or `sequence`, `nop_symbol`, `cmd`, `env` | | As above |
| `screens` | 1 | How many screens, cheapest first; or a list of each one's own `cmd` and `env`, over the dispatch's |
| `batch_size` | 20 | Random knockouts per round of the first screen |
| `max_set_size` | 6 | The largest failing set a shrink follows, and so jackknifes |
| `jackknife_replicates` | 4 | Long trials per knockout, where the jackknife's test is long trials |
| `max_ranking_trials` | 3200 | The most long trials the ranking takes |
| `site_value` | 400 | Long trials another deleted site is worth, to the ranking |
| `replicates` | `harmless_replicates` | The first look of each confirmation |
| `rel_tol`, `abs_tol`, `require_atleast` | 0, 0, `[]` | The margin, as above; a result under the wildtype in a `require_atleast` field is not viable |
| `error_rate`, `indifference`, `futility`, `max_replicates` | | The `sprt` rule's, as above |
| `planned_tests` | 16 | As above; the confirmation makes about `log2` of the pool |
| `reconfirm` | none | A second confirmation, by a costlier trial: its `num_control_trials` (2 or more), its own `env` and `cmd` over the dispatch's, how many of the first's acceptances pass between its tests (`every`, default 1; 0 tests only the prefix the first settles on), whether that count doubles after each test that passes and halves after each that fails (`adaptive`, default false), and any of `replicates`, `rel_tol`, `abs_tol`, `error_rate`, `indifference`, `futility` and `max_replicates` to use in place of the first's |
| `search_seed` | the dispatch's `meta_seed` | Seed of the search's own RNG |

The summary gives the `critical` sites, the `redundant_sets` and the
sets found `adding_up`, with the screen that found each, the sites `kept`
and `released`, whether the whole pool passes the first screen
(`pool_certified`), the `ranking` from least to most costly with its
`effects` and their standard error (`effects_error`, null for a pool too
small to rank), the `predicted_cutoff`, each of the
`confirmations` (with its `reconfirm_replicates`, if it got that far),
and `stats`. It claims no single-deletion minimality:
deleted sites are those the ranking put first, up to the margin.

The search takes many waves, about 50 to 200 on the toys below, as each
bisection step and each look waits for the last.

**Limits.** A first use on a real genome (386 sites, scores with a
standard deviation near the margin's size) showed three:

* The confirmation takes the ranking's order as given. If the pool still
  holds a set that fails together (`pool_certified` is false), the
  bisection stops at the prefix that completes it, and every site ranked
  after stays in, untested.
* Where the jackknife's test is long trials, a failing set of `k` sites
  takes up to `2 * k * jackknife_replicates` of them. Many small,
  overlapping failing sets made that the larger part of the search, over
  more than 600 waves.
* That test makes no allowance for how many knockouts it judges, so a few
  harmless sites are found critical by chance; more
  `jackknife_replicates` make that rarer.

On toy genomes of 100 sites (critical sites, redundant pairs and 20 weak
sites, 200 controls, a margin of two control standard deviations, 10
seeds each),
against `ddmin` judged by `sprt`:

| Toy | Could delete | `staged`: deleted, long trials, screen trials | `ddmin` + `sprt`: deleted, long trials |
|---|---|---|---|
| 5 critical, 5 pairs | 82 | 78, 2,104, 260 | 66.5, 13,684 |
| 30 critical, 3 pairs | 59 | 54.5, 1,705, 302 | 49, 10,605 |
| 5 critical, 10 pairs, 3 triples | 74 | 69, 2,216, 395 | 59.5, 13,102 |
| 80 weak sites | 37 | 24, 2,127, 214 | 24.5, 9,422 |

These toys have no rescue, a screen that never misreads, and normal
noise. Where weak sites interact, `ddmin` deleted a few more (81.5 of 84
against 79.5).

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

The original's noisy evaluators (`BernoulliEvaluator`,
`ConcentrationEvaluator`: pooled Avida competitions, and confidence
sequences with a plug-in variance) are not ported. The sequential rules
above take their place.

Two methods from the 2026-11-13 tiered-knockouts study are left out. The
APT thresholding-bandit allocation did no better than plain round-robin
on most of its landscapes, and worse than `sprt` on all of them. The
multi-fidelity tiers (IISE) helped only where the cheap assay was
unbiased, and deleted fewer sites than `sprt` alone where it was not;
they would also need a bias bound for each tier, which no assay here
supplies.
