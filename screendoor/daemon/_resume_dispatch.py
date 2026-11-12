from ..auxlib._DispatchContext import load_dispatches
from ._select_dispatches import select_dispatches


def resume_dispatch(
    dispatchdir: str, dispatch_uuids: list | None = None
) -> list:
    """Let the daemon tick killed dispatches again.

    Acts on every killed dispatch, or on those whose uuids start with one
    of ``dispatch_uuids``. Returns the uuids resumed. Start the daemon
    afterwards if it has exited.
    """
    done = []
    ctxs = load_dispatches(dispatchdir)
    for ctx in select_dispatches(ctxs, dispatch_uuids):
        if ctx.killed and not ctx.completed:
            ctx.write_dispatch_telemetry({"event": "resumed"})
            done.append(ctx.dispatch_uuid)
    return done
