import contextlib
import os
import tempfile

from ..auxlib._DispatchContext import load_dispatches
from ..daemon._run_busyloop import run_busyloop
from ..daemon._submit_dispatch import submit_dispatch
from ._FakeClock import FakeClock
from ._hooks import INLINE_HOOKS, write_dispatchdir_hooks
from ._register_hook import register_hook


def simulate_dispatch(
    assay,
    assay_kwargs: dict | None = None,
    *,
    fake_trial=None,
    clock: FakeClock | None = None,
    dispatchdir: str | None = None,
    max_ticks: int = 100000,
    submit: bool = True,
    **settings,
) -> dict:
    """Run a whole dispatch on the inline orchestrator in fake time.

    ``assay`` is an expression or a churn function. ``fake_trial(trial) ->
    result`` stands in for each trial's script (``trial`` has key, env,
    cmd and attempt); raising fails the trial with kind ``error``.
    Without it, the scripts really run. The dispatch gets INLINE_HOOKS
    (progress notices silenced), then ``settings``. A dispatchdir without a
    ``screendoor.json`` gets one with DISPATCHDIR_HOOKS.

    To resume an existing ``dispatchdir``, pass ``submit=False`` and, if it
    holds several dispatches, ``dispatch_uuid``.

    Returns ``{"dispatchdir", "dispatch_uuid", "completed", "trials", "memo"}``.
    """
    clock = clock or FakeClock()
    dispatchdir = dispatchdir or tempfile.mkdtemp(prefix="screendoor-sim-")
    if not os.path.exists(os.path.join(dispatchdir, "screendoor.json")):
        write_dispatchdir_hooks(dispatchdir)
    with contextlib.ExitStack() as stack:
        if not clock.active:  # not already entered by the caller
            stack.enter_context(clock)
        uid = settings.get("dispatch_uuid")
        if submit:
            if not isinstance(assay, str):
                assay = register_hook(assay)
            fake = register_hook(fake_trial)
            launch = f"scd.orch.inline.launch(fake_trial={fake})"
            dispatch = {
                "assay": assay,
                "assay_kwargs": assay_kwargs or {},
                "schedule": "* * * * *",
                **INLINE_HOOKS,
                "how_launch": launch,
                "how_notify_progress": "scd.notify.null.notify()",
                **settings,
            }
            uid = submit_dispatch(dispatch, dispatchdir)
        run_busyloop(dispatchdir, max_ticks=max_ticks)
        ctx = next(
            c
            for c in load_dispatches(dispatchdir)
            if uid is None or c.dispatch_uuid == uid
        )
        return {
            "dispatchdir": dispatchdir,
            "dispatch_uuid": ctx.dispatch_uuid,
            "completed": ctx.completed,
            "trials": ctx.read_trials() if ctx.is_setup else [],
            "memo": ctx.read_churn_memo() if ctx.is_setup else [],
        }
