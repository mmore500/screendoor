from ..auxlib._fold_trial_events import fold_trial_events


def fold_trials(
    trial_submissions: list[dict], trial_payloads: list[dict]
) -> list[dict]:
    """Fold the raw trial records churn receives into one dict per trial.

    Each dict has `trial_uuid`, `task_id` (0, 1, 2, ... in request order),
    `key`, `request`, `status` (`requested`, `killed`, `succeeded` or
    `failed`), `state` (`complete` once succeeded or failed, else
    `pending`), `attempt`, `job`, `result`, `channels`, `exit_code` (None
    until the trial ends, and for a lost trial) and the `retries` and
    `kills` counts. `result` is what the trial sent if it succeeded, else
    None; read it with `trial_result`.

    Record order does not matter: a payload from any attempt settles its
    trial, with `completed` taking precedence over `failed`. Trials come in
    order of first request.

    Parameters
    ----------
    trial_submissions : list of dict
        The trial submissions churn received.
    trial_payloads : list of dict
        The trial payloads churn received.

    Returns
    -------
    list of dict
        The folded trials.
    """
    return fold_trial_events([*trial_submissions, *trial_payloads])
