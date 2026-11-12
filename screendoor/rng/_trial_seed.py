from ._derive_seed import derive_seed


def trial_seed(seed: int, trial_uuid: str) -> int:
    """$SCREENDOOR_SEED for a trial; unchanged across relaunches."""
    return derive_seed(seed, "trial", trial_uuid)
