import typing

from ..churn._fold_trials import fold_trials


def all_trials_ready() -> typing.Callable[
    [dict, list[dict], list[dict]], bool
]:
    """Create a `how_unblock_churn` hook that lets churn run once every
    trial submitted so far has succeeded or failed.

    Returns
    -------
    Callable[[dict, list[dict], list[dict]], bool]
        Hook `all_trials_ready(ctx, trial_submissions, trial_payloads)`,
        returning whether no trial is pending.
    """

    def all_trials_ready(
        ctx: dict,
        trial_submissions: list[dict],
        trial_payloads: list[dict],
    ) -> bool:
        trials = fold_trials(trial_submissions, trial_payloads)
        return all(t["state"] == "complete" for t in trials)

    return all_trials_ready
