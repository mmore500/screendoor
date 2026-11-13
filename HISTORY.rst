=======
History
=======

Unreleased
----------

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
