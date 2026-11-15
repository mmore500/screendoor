def batch_trials(trials: list[dict], batchsize: int) -> list[list[dict]]:
    """Split `trials` into consecutive batches of total weight up to
    `batchsize`.

    A trial weighs its request's `weight`, 1 if it has none, so with no
    weights each batch holds `batchsize` trials. A trial heavier than
    `batchsize` gets a batch of its own.

    Parameters
    ----------
    trials : list of dict
        The trials, in order, each with a `request`.
    batchsize : int
        The most weight a batch may hold; the last batch may hold less.

    Returns
    -------
    list of list of dict
        The batches, in order.
    """
    batches, load = [], 0
    for t in trials:
        weight = t["request"].get("weight", 1)
        if not batches or load + weight > batchsize:
            batches.append([])
            load = 0
        batches[-1].append(t)
        load += weight
    return batches
