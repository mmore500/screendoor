import os
import traceback

from ..._worker import latest_request, run_trial
from ...rng._trial_seed import trial_seed


def _run_fake(ctx, trial_uuid: str, fake_trial) -> None:
    write = ctx.hook("how_write_payload")
    events = ctx.hook("how_read_payload")(ctx, raw=True)
    request = latest_request(events, trial_uuid)
    base = {
        "trial_uuid": trial_uuid,
        "attempt": request["attempt"],
        "task_id": request.get("task_id"),
    }
    write(ctx, {"event": "started", **base, "pid": os.getpid()})
    trial = {
        **base,
        "key": request["key"],
        **request["request"],
        "seed": trial_seed(ctx.seed, trial_uuid),
    }
    try:
        result = fake_trial(trial)
    except Exception:
        write(
            ctx,
            {
                "event": "failed",
                **base,
                "kind": "error",
                "exit_code": 1,
                "channels": {},
                "stderr_tail": traceback.format_exc()[-4000:],
            },
        )
    else:
        write(
            ctx,
            {"event": "completed", **base, "result": result, "channels": {}},
        )


def launch(*, fake_trial=None):
    """Run each trial synchronously and in-process, for tests.

    With ``fake_trial``, call ``fake_trial(trial) -> result`` instead of
    running the trial's script.
    """

    def launch(ctx, entries: list, launch_id: str) -> list:
        return [{**e, "job_id": "inline"} for e in entries]

    def after_launched(ctx, entries: list) -> None:
        # trials run once `launched` is recorded, as they would in a job
        for e in entries:
            if fake_trial is None:
                run_trial(ctx, e["trial_uuid"])
            else:
                _run_fake(ctx, e["trial_uuid"], fake_trial)

    launch.after_launched = after_launched
    return launch
