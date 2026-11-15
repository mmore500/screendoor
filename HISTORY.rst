=======
History
=======

Unreleased
----------

* ``scd.record.lockedjsonl`` is folded into ``scd.record.appendjsonl``,
  whose hooks take ``lock=True`` (and ``timeout=``) to read and write under
  ``fcntl`` locks.
* Records no longer carry a ``schema`` field.
* Fixed ``scd.orch.subprocess.throttle``, which never throttled: it looked
  for pidfiles one directory level too shallow for the run directory
  layout.
* ``examples/avida`` runs Avida from the ``ghcr.io/devosoft/avida``
  container through ``singularity exec``, so it needs no local build, and
  labels each dispatch with its organism and policy.
* Assay ``skeletonization.gama``: the Guess/Add/Mate genetic algorithm of
  Rees-Garbutt et al. (2020), with the paper's population sizes as
  defaults. Knockout search summaries can carry policy ``stats``.
* docs/skeletonization.md lists where ``minesweeper`` differs from the
  paper's algorithm.
* Knockout skeletonization judges scores against wildtype controls: each
  policy has ``make_churn(*, num_control_trials=40)``, and its ``churn``
  is made with the default. ``control_test`` is ``t`` (a one-sided t
  prediction bound), ``rank`` (exact Mann-Whitney) or ``mean`` (the old
  rule, and the default with one control), with ``alpha``. Trials get
  ``$wildtype``. The wildtype now runs 40 times by default, not
  ``replicates`` times: replaying an older dispatch launches the extra
  controls, unless it uses ``make_churn(num_control_trials=<its
  replicates>)``.
* ``search_rule`` and ``sweep_rule``: the search and the final sweep each
  look for a ``detectable_loss`` (the default) or need ``noninferiority``
  (a loss shown to be within the margin). With ``noninferiority`` in
  either, each genotype is screened on one replicate for a detectable loss
  (``screen_alpha``), then confirmed on ``replicates`` more by its phase's
  rule. When the rule changes, the sweep judges the search's verdicts again
  from their recorded trials. ``"sweep_rule": null`` skips the sweep.
* ``search_rule`` and ``sweep_rule`` take two sequential noninferiority
  rules: ``sprt`` (Wald's sequential probability ratio test, with an
  indifference zone) and ``mixture`` (the normal-mixture confidence
  sequence of Howard et al. 2021). A genotype's trials come a few at a
  time, doubling from ``replicates`` up to ``max_replicates``, until its
  scores decide. ``error_rate`` bounds the chance of any wrong acceptance
  over the whole search, including the uncertainty in the controls' mean
  and standard deviation. See docs/skeletonization.md.
* Assay ``skeletonization.staged``, for genomes with a cheap pass/fail
  screen for large failures. It finds the critical sites and redundant
  sets by screening random knockouts and shrinking the failures, ranks
  the remaining sites by regression on scored trials of knockouts of many
  sites at once, and confirms one cutoff by the ``sprt`` rule. A failing
  set of several sites is jackknifed, putting each member back in turn,
  to tell a redundant set from small losses adding up; further
  ``screens``, each more sensitive, serve as that test.

0.1.0 (2026-11-12)
------------------

* Cron, busy-loop and self-requeueing Slurm daemons over append-only
  dispatch and trial records; ``submit_dispatch``, ``print_status``,
  ``kill_dispatch``, ``resume_dispatch`` and ``replay_dispatch``.
* Every side effect a hook, with no defaults; record backends
  ``appendjsonl``, ``lockedjsonl`` and ``slottedjsonl``; orchestrators
  ``subprocess``, ``slurm`` and ``inline``; log and Pushover notifiers.
* Assays ``testing.exercise``, ``potentiation.naive_scan``,
  ``skeletonization.jenga`` and the knockout skeletonization policies
  ``skeletonization.ddmin``, ``minesweeper`` and ``hybrid``, ported from
  ``knockout_skeleton``.
