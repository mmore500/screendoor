from ..churn._fold_trials import fold_trials


def all_trials_ready():
    """Unblock churn once every trial submitted so far has succeeded or
    failed (or none has been submitted)."""

    def all_trials_ready(ctx, trial_submissions, trial_payloads) -> bool:
        trials = fold_trials(trial_submissions, trial_payloads)
        return all(t["state"] == "complete" for t in trials)

    return all_trials_ready
