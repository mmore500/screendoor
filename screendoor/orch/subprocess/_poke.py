from __future__ import annotations

import typing

from ._procs import is_alive, pidfile


def poke() -> typing.Callable[[dict, list[dict]], set[str]]:
    """Report trials whose batch's local process is not running.

    Returns
    -------
    Callable[[dict, list], set]
        The ``how_poke`` hook: ``(ctx, trials)`` returns the uuids of the
        trials whose batch is not running.
    """

    def poke(ctx: dict, trials: list[dict]) -> set[str]:
        return {
            t["trial_uuid"]
            for t in trials
            if not (t["job"] and is_alive(pidfile(ctx, t["job"])))
        }

    return poke
