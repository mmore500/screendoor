import logging
import traceback

from ..auxlib._DispatchContext import LEVELS
from ..auxlib._fold_trial_events import fold_trial_events
from ._apply_actions import apply_actions, churn_step, close
from ._launch_trials import submit_trials
from ._notify import flush_batched_notifications, notify

# not yet settled, and not cancelled: poke checks these trials' jobs
IN_PROGRESS = ("requested",)


def _job_label(t: dict) -> str:
    job = t["job"] or {}
    return f"{job.get('name')}[{job.get('index')}]"


def relaunch(ctx, gone: set) -> None:
    """Request vanished trials again, or record them ``failed: lost``.

    A killed attempt does not count against ``trial_maxretry``.
    """
    if not gone:
        return
    vanished = {  # re-read: a result may have landed since the poke
        t["trial_uuid"]: t
        for t in ctx.read_trials()
        if t["trial_uuid"] in gone and t["status"] in (*IN_PROGRESS, "killed")
    }
    entries = []
    for uid, t in vanished.items():
        free = t["status"] == "killed"
        if free or t["retries"] < ctx.record["trial_maxretry"]:
            ctx.log(
                "screendoor: relaunching %s (job %s gone), attempt %d",
                uid[:8],
                _job_label(t),
                t["attempt"] + 1,
            )
            entries.append(
                {
                    "trial_uuid": uid,
                    "attempt": t["attempt"] + 1,
                    "task_id": t["task_id"],
                    "key": t["key"],
                    "request": t["request"],
                }
            )
            continue
        ctx.write_trial_payload(
            {
                "event": "failed",
                "trial_uuid": uid,
                "attempt": t["attempt"],
                "kind": "lost",
                "exit_code": None,
                "channels": {},
                "stderr_tail": f"job {_job_label(t)} vanished "
                f"{t['retries'] + 1} times",
            },
        )
    submit_trials(ctx, entries)


def tick(ctx) -> None:
    """One daemon pass over one open dispatch."""
    if not ctx.is_setup:
        ctx.hook("how_setup")(ctx)
    trials = ctx.read_trials()
    in_progress = [t for t in trials if t["status"] in IN_PROGRESS]
    gone = ctx.hook("how_poke")(ctx, in_progress) if in_progress else ()
    killed = {t["trial_uuid"] for t in trials if t["status"] == "killed"}
    relaunch(ctx, set(gone) | killed)
    throttled = not ctx.hook("how_throttle")(ctx)

    streak = ctx.churn_error_streak
    while ctx.closed is None:
        submissions = ctx.read_trial_submissions()
        payloads = ctx.read_trial_payloads()
        if not ctx.hook("how_unblock_churn")(ctx, submissions, payloads):
            break  # outstanding trials: churn waits for a later tick
        trials = fold_trial_events(submissions + payloads)
        memo = ctx.hook("how_read_memo")(ctx)
        try:
            actions = ctx.churn(ctx.record, submissions, payloads, memo)
            if throttled:  # keep notifications and succeed / fail only
                actions = [
                    a
                    for a in actions
                    if a.get("action") not in ("launch", "memo")
                ]
            wrote_memo = apply_actions(
                ctx, actions, trials, memo, churn_step(memo, submissions)
            )
        except Exception as e:
            streak += 1
            tb = traceback.format_exc()
            logging.error(
                "screendoor: churn raised (%d in a row):\n%s", streak, tb
            )
            ctx.write_dispatch_payload(
                {
                    "event": "churn_error",
                    "streak": streak,
                    "error": repr(e),
                    "traceback": tb[-4000:],
                },
            )
            if streak == 1:
                data = {"dedupe_key": "churn_error"}
                notify(ctx, "failure", f"churn raised: {e!r}", data)
            if streak > ctx.record["churn_maxretry"]:
                reason = f"churn raised {streak} consecutive ticks: {e!r}"
                close(ctx, "failed", reason=reason)
                notify(ctx, "failure", "dispatch failed: churn keeps raising")
            break
        streak = 0
        if not wrote_memo:
            break
    flush_batched_notifications(ctx, LEVELS)
    ctx.churn_error_streak = streak
    ctx.write_dispatch_payload(
        {
            "event": "ticked",
            "churn_error_streak": streak,
            "throttled": throttled,
        },
    )
