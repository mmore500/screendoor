from ..auxlib._DispatchContext import load_dispatches


def resume_dispatch(workdir: str, dispatch_uuids: list | None = None) -> list:
    """Let the daemon tick killed dispatches again.

    Acts on every killed dispatch, or on those in ``dispatch_uuids``.
    Returns the uuids resumed. Start the daemon afterwards if it has exited.
    """
    done = []
    for ctx in load_dispatches(workdir):
        wanted = not dispatch_uuids or ctx.dispatch_uuid in dispatch_uuids
        if ctx.killed and not ctx.closed and wanted:
            ctx.write_dispatch(
                {
                    "event": "resumed",
                },
            )
            done.append(ctx.dispatch_uuid)
    return done
