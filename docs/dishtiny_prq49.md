# DISHTINY prq49

`scd.assaylib.dishtiny_prq49` holds assays for genomes of DISHTINY's prq49
runs: signalgp-lite programs, scored by competition against the wildtype
in `rundishtiny`.

## End-to-end skeletonization

`scd.assaylib.dishtiny_prq49.e2e_skeleton` finds the instructions of a
genome that can be knocked out, turned into nops, with no loss of
fitness. It is one assay and one dispatch: the cheapest, surest tests
come first, so that the costly ones see as little of the genome as
possible. Each stage starts from the positions the stages before it
knocked out, and adds its own.

| Stage | What it knocks out | How |
|---|---|---|
| `strip` | Instructions that are provably dead | One run of the [sgpl-static](https://github.com/mmore500/sgpl-static) pruner. Its nops are taken as they come, with no competition to check them |
| `identity:<kind>` | Units whose knockout shows nothing | The [hybrid](skeletonization.md) search, by a cheap test, with audits by a costly one: see below. No controls, no statistics |
| `fitness:<kind>` | Units whose knockout costs no more than the margin | The [staged](skeletonization.md#staged) search: a screen for lethal knockouts at the `screen` size, then a ranking and a confirmation at the `small` size. What the confirmation accepts is confirmed again at the `full` size (`reconfirm`), every so often and where it settles |
| `final` | Nothing | Scores the finished skeleton against the wildtype at the `full` size, beside the wildtype's full-size controls |

`<kind>` names the stage's units, as `units_of(kind, operations,
knockout)` lists them. A position is live if it is not knocked out and
not a nop, and a module runs from a live global anchor to the next.

| Kind | Units |
|---|---|
| `modules` | The live content of each module, less its global anchor |
| `outputs` | Each live instruction with an effect outside its core: state writes, sends, global regulator sets, forks |
| `calculations` | Each other live instruction that is not a global anchor: arithmetic, logic, constants and random draws, and with them local anchors, inputs and control flow |
| `all` | Each live instruction, global anchors among them: a last pass |

The stages, unless `stages` says otherwise:

1. `strip`
2. `identity:modules`, `identity:outputs`, `identity:calculations`,
   `identity:all`, a `strip` after each
3. `fitness:modules`, `fitness:outputs`, `fitness:calculations`,
   `fitness:all`, a `strip` after each
4. `final`

**Knockouts.** An instruction that draws random numbers is knocked out
with the nop that draws as many (`Nop-1`, `Nop-2`), so that the random
number stream stays as it was and only the drawn value's use is tested.
Any other becomes `Nop-0`.

**Identity.** The search's test is `rundishtiny`'s own
(`TEST_INTERROOT_PHENOTYPE_DIFFERENTIATION`): the knockout and the
wildtype each seed a world of their own, and the two run update by
update on the same random numbers until any cell's resource stockpile
differs. It runs at each size in `divergence`, cheapest first, and a
knockout that shows ends it within a second or two. It is a test for
rejecting: each genome is alone in its world, so it does not show what
only a competitor brings out.

Accepting is the audits' work. An audit takes everything the search has
committed and, after the same test, competes it against the wildtype on
fresh worlds (`identity_worlds`), each of which must end bit-identical to
the wildtype's own competition against itself. Audits are costly, so
they pace themselves (`audit_adaptive`): the first comes after four
commits, each that passes doubles the wait, and each that fails halves
it. A failed audit sifts what was deleted since the last audit that
passed, by halves, as the screen shrinks a failing knockout: a part an
audit accepts stays deleted, and a unit that fails alone goes back in,
for good. Nothing rolls back. A final audit accepts the stage's result,
which holds no commit unaudited.

**Fitness confirmation.** The full-size confirmation is the costliest
test, so it paces itself as the audits do (`reconfirm`'s `every` and
`adaptive`): the bisection for the longest acceptable knockout is by the
small-size confirmation, and the full size judges the longest knockout
accepted so far after every four of its acceptances, and where it
settles. Each full-size test that passes doubles the wait, and each that
fails halves it and bounds the bisection from above. A stage starts
with the wait the fitness stage before it ended on, so that a small size
that proves a poor guide is checked more often from then on. Each
stage's `search` summary gives the wait it ended on, `reconfirm_every`.

**Controls.** A fitness stage's controls are the wildtype against itself,
whatever the stage has knocked out, so each size's controls are run once
and serve every stage: `num_control_trials` at the `small` size,
`num_screen_control_trials` at the `screen` size and
`num_full_control_trials` at the `full`.

**The screen** is one competition on a world of the trial's own, of the
`screen` size: large enough that neither side of a wildtype control dies
out. It grades a knockout lethal if its share of cells is under a
threshold, or none. The threshold is the share a wildtype control falls
below with probability `screen_error_rate`, by a beta distribution fit
to the screen's controls: a share lies between 0 and 1, and the wildtype
against itself is as likely to hold `x` of the cells as `1 - x`, so the
fit is symmetric, from the controls' spread about one half
(`e2e_skeleton.lethal_share`). A knockout that changes anything changes
the whole run, so its share on a world is a fresh draw, whoever won that
world before: the screen picks no worlds, and runs once.

**A strip whose trial fails** is skipped, with a warning: the stages after
it do not need it.

A finished stage is memoized, with the positions it `added` and its
`summary`, so each tick replays only the stage under way.

### Trials

Every trial runs `python3 -m screendoor.assaylib.dishtiny_prq49.run_trial`,
which reads its mode, genome and worlds from `DISHTINY_` variables the
assay sets. The dispatch's `env` gives the rest:

| Variable | |
|---|---|
| `DISHTINY_BINARY` | `rundishtiny` |
| `DISHTINY_GENOME` | The wildtype genome's JSON, with its program at `value0.program` |
| `DISHTINY_CONFIG` | `dishtiny.cfg` |
| `DISHTINY_CACHE` | Optional: a directory, shared by the workers, that keeps each competition run on a fixed world. Without it, an identity trial reruns the wildtype's own competitions |
| `DISHTINY_PRUNER` | Optional: the command that runs the pruner; `{dir}` stands for the trial's working directory. Default `singularity run --cleanenv docker://ghcr.io/mmore500/sgpl-static:v0.3.2` |
| `DISHTINY_PROJECT`, `DISHTINY_PERIPHERAL` | Optional: the pruner's `--project` and `--peripheral`. Default: the DISHTINY commit and peripheral of the pruner's README |
| `DISHTINY_SERIES`, `DISHTINY_STINT` | Optional: 16005, 100 |

The pruner fetches its project and peripheral, so its trial needs the
network, or local copies named by those variables.

### Assay kwargs

| Key | Default | Meaning |
|---|---|---|
| `operations` | required | The wildtype program's operations, in order |
| `env` | `{}` | As above |
| `cmd` | the `run_trial` command | Every trial's script |
| `stages` | as above | The stages, in order |
| `small` | `[12288, 36]` | Updates and cells of the cheap competitions: rankings, first confirmations |
| `screen` | `[8192, 576]` | Updates and cells of the screen's one competition |
| `full` | `[24576, 1024]` | Updates and cells of the reconfirmations and the final check |
| `divergence` | `[[2048, 100], [8192, 100]]` | The updates and cells of each side-by-side test an identity trial runs, cheapest first |
| `identity_worlds` | four of `[12288, 36]`, two of `[24576, 64]` | The size of each world an identity audit competes in, cheapest first; it stops at the first that differs |
| `identity` | `{"batch_size": 56, "audit_every": 4, "audit_adaptive": true, "max_rollbacks": 1000}` | Kwargs of the hybrid search, over these |
| `fitness` | `{"batch_size": 40, "abs_tol": 0.15, "jackknife_replicates": 32, "max_replicates": 1024}` | Kwargs of the staged search, over these. `abs_tol` is of a share of cells |
| `reconfirm` | `{}` | The staged search's `reconfirm` kwargs, as its own `abs_tol` or `max_replicates`; `every` here sets every stage's starting wait, and `adaptive` whether it changes |
| `num_control_trials`, `num_screen_control_trials`, `num_full_control_trials` | 400, 100, 100 | Wildtype controls of each size |
| `screen_error_rate` | 0.001 | The chance that the screen grades a harmless knockout lethal |
| `run_seconds` | `{"small": 60, "screen": 600, "full": 2400}` | The seconds after which `rundishtiny` ends a competition of each size where it stands (its `RUN_SECONDS`) |
| `overhead_seconds` | 10 | The seconds past its `run_seconds` after which a competition still going is killed |
| `pruner_timeout` | 1800 | The seconds the pruner may take, before it is killed and its trial fails |
| `final_replicates` | 64 | Full-size competitions of the finished skeleton |
| `world_seed` | 0 | Added to every fixed world's seed |

The summary gives the `knockout` and the `skeleton` (the live positions
left), their counts, and each stage's `added` count and `summary`: the
units deleted and retained by label, and the search's own summary.

### Batches

`rundishtiny` ends every competition after a set time, by its size
(`run_seconds`, its own `RUN_SECONDS`, beside `RUN_UPDATES`): the run
stops where it stands, and its result is of the updates it ran, marked
`cut_short`. A run still going `overhead_seconds` later is killed. A
world of another size, as an identity audit runs, gets the small size's
seconds in proportion to updates times cells, and at least 20; a
side-by-side test, which `RUN_SECONDS` does not end, is killed at twice
that, for its two worlds.

A run that was killed, or cut short where every update matters, shows
nothing, and its trial is *inconclusive*: an identity trial does not
accept, a screen does not fail, and a score is not viable, which the
search takes as a knockout it cannot accept. Each stage's summary counts
its `inconclusive_trials`, with a warning if there are any: many of them
mean limits too short for the nodes, and knockouts kept for no reason.

A trial's `weight` is the seconds it may take in all: its competition's
`run_seconds` and `overhead_seconds`; for an identity trial, its
side-by-side tests' and, in an audit, twice its worlds', as it may run
the wildtype's own competitions too; for a strip, `pruner_timeout`. `trial_batchsize` is then the longest a job's trials
can run, in seconds, whatever the nodes: for jobs that must end within
3.5 hours,

    trial_batchsize = 12000

which leaves ten minutes of the job to spare, with `trial_batch_timeout`
at the scheduler's own limit, as 4 hours. On the laptop measured below,
a job of screens then takes about an hour and a half, and a job of small
competitions about 45 minutes, as each takes a half or a quarter of its
seconds; a job holds four full-size competitions, about an hour. A search
round with less work than a job makes a shorter one; rounds are wider
with a larger `batch_size`.

Each default is about twice the longest such run seen on that laptop: a
full-size competition takes 10 to 18 minutes there, and gets 40. Time a
competition of each size on a compute node before a long run, and set
`run_seconds` to suit: a run cut short scores only the updates that fit.

### Measured

On one laptop, for the genome of series 16005, stint 100 (1,521
instructions), with 14 competitions running at once: a small competition
takes about 15 seconds, a screen's about 285 (20 to 80 for a lethal
knockout, as a run ends once one side is gone), a full-size one 10 to
18 minutes, and the pruner about 100 seconds of wall time on the whole
genome. In 28 screen-size controls, the wildtype's share ran from 0.24
to 0.69 (standard deviation 0.12), which puts the threshold near 0.15;
two knockouts known to be lethal held no cells in any of 14 runs. A
prototype of the strip and fitness stages alone, all at the small size,
took 76 CPU hours and left 191 instructions, 107 of them bare global
anchors; identity stages before them cleared about 500 more instructions
than the pruner in an earlier prototype.

### Limits

* Identity is only as good as its worlds: an instruction that never
  runs on them passes. Each audit's fresh worlds, and the fitness stages
  after, are the check.
* The side-by-side test's worlds all start from one seed, fixed in
  `rundishtiny`; only their size varies.
* The screen runs once, so about `screen_error_rate` of the harmless
  knockouts it sees are graded lethal, and stay in.
* A fitness stage inherits the staged search's limits: its confirmation
  stops at the first knockout that fails, and the units ranked after it
  stay in, untested.
* Each fitness stage's tests carry their own `error_rate`; nothing
  bounds the whole run's. The `final` stage reports the skeleton's score
  beside the controls', and judges nothing.
