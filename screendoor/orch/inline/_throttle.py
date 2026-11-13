import typing


def throttle() -> typing.Callable[[dict], bool]:
    """Create a `how_throttle_churn` hook that never throttles: inline
    trials end during launch.

    Returns
    -------
    Callable[[dict], bool]
        Hook `throttle(ctx)`, always returning True.
    """

    def throttle(ctx: dict) -> bool:
        return True

    return throttle
