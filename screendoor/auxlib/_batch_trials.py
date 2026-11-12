def batch_trials(trials: list[dict], batchsize: int) -> list[list[dict]]:
    """Split ``trials`` into consecutive batches of ``batchsize``.

    Parameters
    ----------
    trials : list of dict
        The trials, in order.
    batchsize : int
        Trials per batch; the last may have fewer.

    Returns
    -------
    list of list of dict
        The batches, in order.
    """
    return [
        trials[i : i + batchsize] for i in range(0, len(trials), batchsize)
    ]
