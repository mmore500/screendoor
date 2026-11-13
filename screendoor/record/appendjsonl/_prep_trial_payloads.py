import typing


def prep_trial_payloads() -> typing.Callable[[dict, int], None]:
    """Create a `how_prep_trial_payloads` hook that does nothing: an
    appended `trial_payloads.jsonl` needs no room made in advance.

    Returns
    -------
    Callable[[dict, int], None]
        Hook `prep_trial_payloads(ctx, n_trials)`.
    """

    def prep_trial_payloads(ctx: dict, n_trials: int) -> None:
        pass

    return prep_trial_payloads
