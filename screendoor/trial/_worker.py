import logging

from ..auxlib._DispatchContext import load_dispatches
from ._run_trial import run_trial


def worker(dispatchdir: str, dispatch_uuid: str, trial_uuids: list) -> int:
    """Run trials one after another; return a process exit code.

    One trial crashing does not stop the rest of the batch.
    """
    ctxs = {c.dispatch_uuid: c for c in load_dispatches(dispatchdir)}
    if dispatch_uuid not in ctxs:
        raise LookupError(f"no dispatch {dispatch_uuid} in {dispatchdir}")
    ctx = ctxs[dispatch_uuid]
    submissions = ctx.read_trial_submissions()
    exit_code = 0
    for trial_uuid in trial_uuids:
        try:
            run_trial(ctx, trial_uuid, submissions)
        except Exception:
            logging.exception("screendoor: trial %s crashed", trial_uuid)
            exit_code = 1
    return exit_code
