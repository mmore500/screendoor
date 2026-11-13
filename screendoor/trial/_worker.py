import logging

from ..auxlib._DispatchContext import load_dispatch
from ._run_trial import run_trial


def worker(
    dispatchdir: str, dispatch_uuid: str, trial_uuids: list[str]
) -> int:
    """Run trials one after another and return a process exit code.

    One trial crashing does not stop the rest of the batch.

    Parameters
    ----------
    dispatchdir : str
        Path of the dispatchdir.
    dispatch_uuid : str
        The dispatch the trials belong to.
    trial_uuids : list of str
        The trials to run, in order.

    Returns
    -------
    int
        1 if a trial crashed, else 0.

    Raises
    ------
    LookupError
        If `dispatchdir` has no dispatch `dispatch_uuid`.
    """
    ctx = load_dispatch(dispatchdir, dispatch_uuid)
    submissions = ctx.read_trial_submissions()
    exit_code = 0
    for trial_uuid in trial_uuids:
        try:
            run_trial(ctx, trial_uuid, submissions)
        except Exception:
            logging.exception("screendoor: trial %s crashed", trial_uuid)
            exit_code = 1
    return exit_code
