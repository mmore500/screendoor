import contextlib
import tempfile

from ..auxlib._DispatchContext import load_dispatches
from ..daemon._run_busyloop import run_busyloop
from ..daemon._submit_dispatch import submit_dispatch
from ._FakeClock import FakeClock
from ._register_hook import register_hook


def simulate_dispatch(
    assay,
    assay_kwargs: dict | None = None,
    *,
    fake_trial=None,
    clock: FakeClock | None = None,
    workdir: str | None = None,
    max_ticks: int = 100000,
    submit: bool = True,
    **settings,
) -> dict:
    """Run a whole dispatch on the inline orchestrator in fake time.

    ``assay`` is an expression or a churn function. ``fake_trial(trial) ->
    result`` stands in for each trial's script (``trial`` has key, env,
    cmd, seed and attempt); raising fails the trial with kind ``error``.
    Without it, the scripts really run. Other ``settings`` go into the
    dispatch.

    To resume an existing ``workdir``, pass ``submit=False`` and, if it
    holds several dispatches, ``dispatch_uuid``.

    Returns ``{"workdir", "dispatch_uuid", "closed", "trials", "memo"}``.
    """
    clock = clock or FakeClock()
    workdir = workdir or tempfile.mkdtemp(prefix="screendoor-sim-")
    with contextlib.ExitStack() as stack:
        if clock._saved is None:  # not already entered by the caller
            stack.enter_context(clock)
        uid = settings.get("dispatch_uuid")
        if submit:
            if not isinstance(assay, str):
                assay = register_hook(assay)
            fake = register_hook(fake_trial)
            launch = f"scd.orchestrate.inline.launch(fake_trial={fake})"
            dispatch = {
                "assay": assay,
                "assay_kwargs": assay_kwargs or {},
                "schedule": "* * * * *",
                "how_launch": launch,
                "how_poke": "scd.orchestrate.inline.poke()",
                "how_kill": "scd.orchestrate.inline.kill()",
                "how_notify_progress": "scd.notify.null.notify()",
                **settings,
            }
            uid = submit_dispatch(dispatch, workdir)
        run_busyloop(workdir, max_ticks=max_ticks)
        ctx = next(
            c
            for c in load_dispatches(workdir)
            if uid is None or c.dispatch_uuid == uid
        )
        return {
            "workdir": workdir,
            "dispatch_uuid": ctx.dispatch_uuid,
            "closed": ctx.closed,
            "trials": ctx.hook("how_read_payload")(ctx)
            if ctx.is_setup
            else [],
            "memo": ctx.hook("how_read_memo")(ctx) if ctx.is_setup else [],
        }
