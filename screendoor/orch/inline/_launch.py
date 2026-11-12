import logging
import os

from ...trial._run_trial import latest_request, run_trial


def _run_fake(ctx, trial_uuid: str, fake_trial) -> None:
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


def launch(*, fake_trial=None):
    """Run each trial synchronously and in-process, for tests.

    Trials run once their submissions are recorded, as they would in a
    job. With ``fake_trial``, call ``fake_trial(trial) -> result`` instead
    of running the trial's script; raising fails the trial.
    """

    def launch(ctx, name: str, batches: list) -> None:
        for batch in batches:
            for e in batch:
                try:  # as the worker does: one trial's crash is its own
                    if fake_trial is None:
                        run_trial(ctx, e["trial_uuid"])
                    else:
                        _run_fake(ctx, e["trial_uuid"], fake_trial)
                except Exception:
                    logging.exception(
                        "screendoor: trial %s crashed", e["trial_uuid"]
                    )

    return launch
