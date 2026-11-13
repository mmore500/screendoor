import typing

from ._procs import is_alive, pidfile


def poke() -> typing.Callable[[dict, list[dict]], set[str]]:
    """Create a `how_poke` hook that reports trials whose batch process is
    not running.

    Returns
    -------
    Callable[[dict, list[dict]], set[str]]
        Hook `poke(ctx, trials)`, returning the `trial_uuid` of each trial
        whose batch is not running.
    """

    def poke(ctx: dict, trials: list[dict]) -> set[str]:
        return {
            t["trial_uuid"]
            for t in trials
            if not (t["job"] and is_alive(pidfile(ctx, t["job"])))
        }

    return poke
