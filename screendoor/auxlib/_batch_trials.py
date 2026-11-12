def batch_trials(trials: list, batchsize: int) -> list:
    """Split ``trials`` into consecutive batches of ``batchsize``."""
    return [
        trials[i : i + batchsize] for i in range(0, len(trials), batchsize)
    ]
