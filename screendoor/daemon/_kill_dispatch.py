from ..auxlib._DispatchContext import load_dispatches
from ._run_tick_once import workdir_lock
from ._tick import IN_PROGRESS


def kill_dispatch(workdir: str, dispatch_uuids: list | None = None) -> list:
    """Cancel in-progress trials and pause their dispatches.

    Acts on every open dispatch, or on those in ``dispatch_uuids``. A
    killed dispatch is not completed and its trials are not failed: the daemon
    skips it until resume_dispatch, then relaunches the cancelled trials
    without counting a retry. Safe to repeat. Returns the uuids acted on.
    """
    done = []
    with workdir_lock(workdir, wait=True):  # not in the middle of a tick
        for ctx in load_dispatches(workdir):
            wanted = not dispatch_uuids or ctx.dispatch_uuid in dispatch_uuids
            if ctx.completed or not wanted:
                continue
            if not ctx.killed:  # pause first, so that no tick relaunches
                ctx.write_dispatch_telemetry(
                    {
                        "event": "killed",
                    },
                )
            trials = ctx.read_trials() if ctx.is_setup else []
            trials = [t for t in trials if t["status"] in IN_PROGRESS]
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
