import contextlib
import os
import tempfile
import typing

from ..auxlib._DispatchContext import load_dispatches
from ..daemon._run_busyloop import run_busyloop
from ..daemon._submit_dispatch import submit_dispatch
from ._FakeClock import FakeClock
from ._hooks import INLINE_HOOKS, write_dispatchdir_hooks
from ._register_hook import register_hook


def simulate_dispatch(
    assay: str | typing.Callable[..., list[dict]],
    assay_kwargs: dict | None = None,
    *,
    fake_trial: typing.Callable[[dict], typing.Any] | None = None,
    clock: FakeClock | None = None,
    dispatchdir: str | None = None,
    max_ticks: int = 100000,
    submit: bool = True,
    **settings: typing.Any,
) -> dict:
    """Run a whole dispatch on the inline orchestrator in fake time.

    The dispatch gets `INLINE_HOOKS`, with progress notices silenced, then
    `settings`. A dispatchdir without a `dispatch_hooks.json` gets one
    with `DISPATCHDIR_HOOKS`. To resume an existing dispatchdir, pass
    `submit=False` and, if it holds several dispatches, `dispatch_uuid`.

    Parameters
    ----------
    assay : str or Callable
        The dispatch's `assay`: an expression, or a churn function.
    assay_kwargs : dict or None, default None
        The dispatch's `assay_kwargs`.
    fake_trial : Callable[[dict], Any] or None, default None
        A function called as `fake_trial(trial)` in place of each trial's
        script, returning the trial's result; raising fails the trial.
        `trial` carries the trial's `key`, `cmd`, `env` and `attempt`.
        None runs the scripts.
    clock : FakeClock or None, default None
        The clock to run in, entered here unless already entered; a new one
        if None.
    dispatchdir : str or None, default None
        Path of the dispatchdir; a fresh temporary directory if None.
    max_ticks : int, default 100000
        Stop the daemon after this many passes.
    submit : bool, default True
        Whether to submit a new dispatch, rather than resume one.
    **settings
        Further dispatch fields, set over `INLINE_HOOKS`.

    Returns
    -------
    dict
        `{"dispatchdir", "dispatch_uuid", "completed", "trials", "memo"}`
        of the dispatch run.
    """
    clock = clock or FakeClock()
    dispatchdir = dispatchdir or tempfile.mkdtemp(prefix="screendoor-sim-")
    if not os.path.exists(os.path.join(dispatchdir, "dispatch_hooks.json")):
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
