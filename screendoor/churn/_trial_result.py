import typing


def trial_result(trial: dict) -> typing.Any:
    """Return a folded trial's result.

    A trial has a result only if it succeeded and sent a non-null
    `payload`.

    Parameters
    ----------
    trial : dict
        A folded trial, as from `fold_trials`.

    Returns
    -------
    Any
        The trial's `result`.

    Raises
    ------
    RuntimeError
        If the trial has no result.
    """
    if trial["result"] is None:
        raise RuntimeError(
            f"trial {trial['trial_uuid'][:8]} ({trial['status']}, "
            f"key {trial['key']}) has no result"
        )
    return trial["result"]
