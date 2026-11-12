from __future__ import annotations

import contextlib
import os
import typing


def setup() -> typing.Callable[[dict], None]:
    """Make the dispatchdir private (mode 700): whoever can append to its
    dispatch records can run code as the daemon.

    Returns
    -------
    Callable[[dict], None]
        The ``how_setup`` hook: ``(ctx)`` makes ``ctx["dispatchdir"]`` mode
        700, if it can.
    """

    def setup(ctx: dict) -> None:
        with contextlib.suppress(OSError):
            os.chmod(ctx["dispatchdir"], 0o700)

    return setup
