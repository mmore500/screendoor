import contextlib
import os


def setup():
    """Make the dispatchdir private (mode 700): whoever can append to its
    dispatch records can run code as the daemon."""

    def setup(ctx) -> None:
        with contextlib.suppress(OSError):
            os.chmod(ctx.dispatchdir, 0o700)

    return setup
