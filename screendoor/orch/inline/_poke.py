from __future__ import annotations

import typing


def poke() -> typing.Callable[[dict, list[dict]], set[str]]:
    """Inline trials end during launch, so an unsettled one is gone.

    Returns
    -------
    Callable[[dict, list], set]
        The ``how_poke`` hook: ``(ctx, trials)`` returns the uuid of every
        trial in ``trials``.
    """

    def poke(ctx: dict, trials: list[dict]) -> set[str]:
        return {t["trial_uuid"] for t in trials}

    return poke
