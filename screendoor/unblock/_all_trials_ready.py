from __future__ import annotations

import typing

from ..churn._fold_trials import fold_trials


def all_trials_ready() -> typing.Callable[
    [dict, list[dict], list[dict]], bool
]:
    """Unblock churn once every trial submitted so far has succeeded or
    failed (or none has been submitted).

    Returns
    -------
    Callable[[dict, list[dict], list[dict]], bool]
        The ``how_unblock_churn`` hook: ``(ctx, trial_submissions,
        trial_payloads)`` returns whether no trial is pending.
    """

    def all_trials_ready(
        ctx: dict,
        trial_submissions: list[dict],
        trial_payloads: list[dict],
    ) -> bool:
        trials = fold_trials(trial_submissions, trial_payloads)
        return all(t["state"] == "complete" for t in trials)

    return all_trials_ready
