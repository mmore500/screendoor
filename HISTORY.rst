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
