import contextlib
import os
import typing


def setup() -> typing.Callable[[dict], None]:
    """Create a `how_setup` hook that makes the dispatchdir private (mode
    700).

    Hook expressions are evaluated from the dispatchdir's records, so
    whoever can append to them can run code as the daemon.

    Returns
    -------
    Callable[[dict], None]
        Hook `setup(ctx)`, which changes the mode of `ctx["dispatchdir"]`
        if it can.
    """

    def setup(ctx: dict) -> None:
        with contextlib.suppress(OSError):
            os.chmod(ctx["dispatchdir"], 0o700)

    return setup
