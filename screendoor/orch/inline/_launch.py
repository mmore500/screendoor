import logging
import os
import typing

from ...auxlib._DispatchContext import DispatchContext, load_dispatch
from ...trial._run_trial import latest_request
from ...trial._worker import worker


def _run_fake(
    ctx: DispatchContext,
    trial_uuid: str,
    fake_trial: typing.Callable[[dict], typing.Any],
) -> None:
    request = latest_request(ctx.read_trial_submissions(), trial_uuid)
    base = {
        "trial_uuid": trial_uuid,
        "attempt": request["attempt"],
        "task_id": request["task_id"],
        "channels": {},
    }
    ctx.write_trial_telemetry({"event": "started", **base, "pid": os.getpid()})
    trial = {**base, "key": request["key"], **request["request"]}
    try:
        result = fake_trial(trial)
    except Exception:
        logging.exception("screendoor: fake trial %s raised", trial_uuid)
        ctx.write_trial_payload({"event": "failed", **base, "exit_code": 1})
    else:
        ctx.write_trial_payload(
            {"event": "completed", **base, "exit_code": 0, "result": result}
        )


def launch(
    *, fake_trial: typing.Callable[[dict], typing.Any] | None = None
) -> typing.Callable[[dict, str, list[list[dict]]], None]:
    """Create a `how_launch` hook that runs each batch in-process, as the
    worker would.

    Parameters
    ----------
    fake_trial : Callable[[dict], Any] or None, default None
        A function called as `fake_trial(trial)` in place of each trial's
        script, returning the trial's result; raising fails the trial.
        `trial` carries the trial's `trial_uuid`, `attempt`, `task_id`,
        `key`, `cmd` and `env`. None runs the scripts.

    Returns
    -------
    Callable[[dict, str, list[list[dict]]], None]
        Hook `launch(ctx, name, batches)`, which runs every trial in
        `batches` to completion, logging any that crashes.
    """

    def launch(ctx: dict, name: str, batches: list[list[dict]]) -> None:
        uuids = [e["trial_uuid"] for batch in batches for e in batch]
        if fake_trial is None:
            worker(ctx["dispatchdir"], ctx["dispatch_uuid"], uuids)
            return
        dispatch = load_dispatch(ctx["dispatchdir"], ctx["dispatch_uuid"])
        for trial_uuid in uuids:
            try:  # as the worker does: one trial's crash is its own
                _run_fake(dispatch, trial_uuid, fake_trial)
            except Exception:
                logging.exception("screendoor: trial %s crashed", trial_uuid)

    return launch
