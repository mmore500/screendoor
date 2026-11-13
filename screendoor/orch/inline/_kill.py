import typing


def kill() -> typing.Callable[[dict, list[dict]], None]:
    """Create a `how_kill` hook that does nothing: inline trials end during
    launch, so there is never one to cancel.

    Returns
    -------
    Callable[[dict, list[dict]], None]
        Hook `kill(ctx, trials)`.
    """

    def kill(ctx: dict, trials: list[dict]) -> None:
        pass

    return kill
