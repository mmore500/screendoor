import typing


def poke() -> typing.Callable[[dict, list[dict]], set[str]]:
    """Create a `how_poke` hook that reports every unsettled trial as gone:
    inline trials end during launch.

    Returns
    -------
    Callable[[dict, list[dict]], set[str]]
        Hook `poke(ctx, trials)`, returning the `trial_uuid` of every trial
        in `trials`.
    """

    def poke(ctx: dict, trials: list[dict]) -> set[str]:
        return {t["trial_uuid"] for t in trials}

    return poke
