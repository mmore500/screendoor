from ..auxlib._DispatchContext import load_dispatches
from ._select_dispatches import select_dispatches


def resume_dispatch(
    dispatchdir: str, dispatch_uuids: list[str] | None = None
) -> list[str]:
    """Let the daemon tick killed dispatches again.

    Acts on every killed dispatch, or on those whose uuids start with one
    of ``dispatch_uuids``. Returns the uuids resumed. Start the daemon
    afterwards if it has exited.

    Parameters
    ----------
    dispatchdir : str
        The dispatchdir holding the dispatches.
    dispatch_uuids : list of str or None, default None
        Prefixes of the uuids to act on; None or empty for every one.

    Returns
    -------
    list of str
        The dispatch_uuids resumed.

    Raises
    ------
    LookupError
        If a prefix matches no dispatch, or more than one.
    """
    done = []
    ctxs = load_dispatches(dispatchdir)
    for ctx in select_dispatches(ctxs, dispatch_uuids):
        if ctx.killed and not ctx.completed:
            ctx.write_dispatch_telemetry({"event": "resumed"})
            done.append(ctx.dispatch_uuid)
    return done
