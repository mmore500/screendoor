import logging
import os
import platform
import shutil

from .. import __version__
from ..auxlib._DispatchContext import DispatchContext


def setup_dispatch(ctx: DispatchContext) -> None:
    """Start the dispatch's run directory afresh, call `how_setup` and
    record a `setup` event.

    A run directory left by an earlier dispatch with the same labels is
    deleted first; bump `meta_redo` to keep it.

    Parameters
    ----------
    ctx : DispatchContext
        The dispatch setting up.
    """
    if os.path.lexists(ctx.run_dir):
        logging.warning("screendoor: clearing %s", ctx.run_dir)
        shutil.rmtree(ctx.run_dir)
    os.makedirs(os.path.join(ctx.run_dir, "trials"))
    ctx.call_hook("how_setup")
    ctx.write_dispatch_telemetry(
        {
            "event": "setup",
            "run_dir": ctx.run_dir,
            "screendoor_version": __version__,
            "python_version": platform.python_version(),
        },
    )
    ctx.is_setup = True
