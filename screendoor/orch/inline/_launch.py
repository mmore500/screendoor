import os
import traceback

from ...trial._run_trial import latest_request, run_trial


def _run_fake(ctx, trial_uuid: str, fake_trial) -> None:
    request = latest_request(ctx.read_trial_submissions(), trial_uuid)
    base = {
        "trial_uuid": trial_uuid,
        "attempt": request["attempt"],
        "task_id": request.get("task_id"),
    }
    ctx.hook("how_write_trial_telemetry")(
        ctx, {"event": "started", **base, "pid": os.getpid()}
    )
    trial = {**base, "key": request["key"], **request["request"]}
    try:
        result = fake_trial(trial)
    except Exception:
        ctx.write_trial_payload(
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
        ctx.write_trial_payload(
            {"event": "completed", **base, "result": result, "channels": {}},
        )


def launch(*, fake_trial=None):
    """Run each trial synchronously and in-process, for tests.

    Trials run once their submissions are recorded, as they would in a
    job. With ``fake_trial``, call ``fake_trial(trial) -> result`` instead
    of running the trial's script.
    """

    def launch(ctx, name: str, batches: list) -> None:
        for batch in batches:
            for e in batch:
                if fake_trial is None:
                    run_trial(ctx, e["trial_uuid"])
                else:
                    _run_fake(ctx, e["trial_uuid"], fake_trial)

    return launch
