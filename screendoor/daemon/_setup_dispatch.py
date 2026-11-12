import logging
import os
import platform
import shutil

from .. import __version__


def setup_dispatch(ctx) -> None:
    """Start the dispatch's run directory afresh, then call how_setup and
    record ``setup``.

    A run directory left by an earlier dispatch with the same labels is
    deleted first: bump ``meta_redo`` to keep it.
    """
    if os.path.lexists(ctx.run_dir):
        logging.warning("screendoor: clearing %s", ctx.run_dir)
        shutil.rmtree(ctx.run_dir)
    os.makedirs(os.path.join(ctx.run_dir, "trials"))
    ctx.hook("how_setup")(ctx)
    ctx.write_dispatch_telemetry(
        {
            "event": "setup",
            "run_dir": ctx.run_dir,
            "screendoor_version": __version__,
            "python_version": platform.python_version(),
        },
    )
    ctx.is_setup = True
