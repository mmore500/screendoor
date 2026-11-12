from ..auxlib._DispatchContext import load_dispatches
from ._dispatchdir_lock import dispatchdir_lock
from ._select_dispatches import select_dispatches


def kill_dispatch(
    dispatchdir: str, dispatch_uuids: list | None = None
) -> list:
    """Cancel in-progress trials and pause their dispatches.

    Acts on every open dispatch, or on those whose uuids start with one
    of ``dispatch_uuids``. A
    killed dispatch is not completed and its trials are not failed: the daemon
    skips it until resume_dispatch, then relaunches the cancelled trials
    without counting a retry. Safe to repeat. Returns the uuids acted on.
    """
    done = []
    with dispatchdir_lock(dispatchdir, wait=True):  # not mid-tick
        ctxs = load_dispatches(dispatchdir)
        for ctx in select_dispatches(ctxs, dispatch_uuids):
            if ctx.completed:
                continue
            if not ctx.killed:  # pause first, so that no tick relaunches
                ctx.write_dispatch_telemetry(
                    {
                        "event": "killed",
                    },
                )
            trials = ctx.read_trials() if ctx.is_setup else []
            trials = [t for t in trials if t["status"] == "requested"]
            if trials:
                ctx.hook("how_kill")(ctx, trials)
            for t in trials:
                ctx.write_trial_submission(
                    {
                        "event": "killed",
                        "trial_uuid": t["trial_uuid"],
                        "attempt": t["attempt"],
                        "job": t["job"],
                    },
                )
            ctx.log(
                "screendoor: killed dispatch %s, cancelling %d trials",
                ctx.dispatch_uuid[:8],
                len(trials),
            )
            done.append(ctx.dispatch_uuid)
    return done
