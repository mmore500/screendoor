from __future__ import annotations

import typing


def kill() -> typing.Callable[[dict, list[dict]], None]:
    """Inline trials end during launch, so there is never one to cancel.

    Returns
    -------
    Callable[[dict, list], None]
        The ``how_kill`` hook: ``(ctx, trials)`` does nothing.
    """

    def kill(ctx: dict, trials: list[dict]) -> None:
        pass

    return kill
