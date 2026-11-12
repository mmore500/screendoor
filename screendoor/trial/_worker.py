import logging
import os

from ..auxlib._DispatchContext import load_dispatches
from ._run_trial import run_trial


def worker(workdir: str, dispatch_uuid: str, trials: list) -> int:
    """Run trials (uuids or trial directories) one after another.

    Returns a process exit code.
    """
    ctxs = {c.dispatch_uuid: c for c in load_dispatches(workdir)}
    if dispatch_uuid not in ctxs:
        raise LookupError(f"no dispatch {dispatch_uuid} in {workdir}")
    exit_code = 0
    for trial in trials:
        trial_uuid = os.path.basename(os.path.normpath(trial))
        try:
            run_trial(ctxs[dispatch_uuid], trial_uuid)
        except Exception:
            logging.exception("screendoor: trial %s crashed", trial_uuid)
            exit_code = 1
    return exit_code
