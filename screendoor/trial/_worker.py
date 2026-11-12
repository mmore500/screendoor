import logging
import os

from ..auxlib._DispatchContext import load_dispatches
from ._run_trial import run_trial


def worker(dispatchdir: str, dispatch_uuid: str, trials: list) -> int:
    """Run trials (uuids or trial directories) one after another.

    Returns a process exit code.
    """
    ctxs = {c.dispatch_uuid: c for c in load_dispatches(dispatchdir)}
    if dispatch_uuid not in ctxs:
        raise LookupError(f"no dispatch {dispatch_uuid} in {dispatchdir}")
    ctx = ctxs[dispatch_uuid]
    submissions = ctx.read_trial_submissions()
    exit_code = 0
    for trial in trials:
        trial_uuid = os.path.basename(os.path.normpath(trial))
        try:
            run_trial(ctx, trial_uuid, submissions)
        except Exception:
            logging.exception("screendoor: trial %s crashed", trial_uuid)
            exit_code = 1
    return exit_code
