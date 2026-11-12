from ._derive_seed import derive_seed


def step_seed(seed: int, n_memo: int, n_trials: int) -> int:
    """Seed of the churn step stream for the recorded state sizes."""
    return derive_seed(seed, "churn", n_memo, n_trials)
