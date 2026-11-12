from ..churn._fold_trials import fold_trials


def all_trials_ready(ctx, trial_submissions: list, trial_payloads: list):
    """Whether no submitted trial is still outstanding.

    The default ``how_unblock_churn``: churn is called only once every
    trial submitted so far has succeeded or failed (or none has been
    submitted yet).
    """
    trials = fold_trials(trial_submissions, trial_payloads)
    return all(t["state"] == "complete" for t in trials)
