from __future__ import annotations

import typing


def throttle() -> typing.Callable[[dict], bool]:
    """Never throttle: inline trials end during launch.

    Returns
    -------
    Callable[[dict], bool]
        The ``how_throttle_churn`` hook: ``(ctx)`` always returns True.
    """

    def throttle(ctx: dict) -> bool:
        return True

    return throttle
