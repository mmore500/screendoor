from ..auxlib._fold_trial_events import fold_trial_events


def fold_trials(trial_submissions: list, trial_payloads: list) -> list:
    """One dict per trial, from churn's raw trial submissions and payloads.

    Each dict has ``trial_uuid``, ``task_id``, ``key``, ``request``,
    ``status`` (``requested``, ``killed``, ``succeeded`` or ``failed``),
    ``state`` (``complete`` once succeeded or failed, else ``pending``),
    ``attempt``, ``job``, ``result``, ``channels``, ``exit_code`` (None
    until the trial ends, and for a lost one) and the ``retries`` and
    ``kills`` counts. ``result`` is what the trial sent if it succeeded,
    else None; read it with scd.churn.trial_result. Record order does not
    matter: a payload from any attempt settles its trial, ``completed``
    over ``failed``. Trials come in order of first request.
    """
    return fold_trial_events([*trial_submissions, *trial_payloads])
