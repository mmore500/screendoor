import logging
import traceback

from ..auxlib._DispatchContext import DispatchContext
from ..auxlib._fold_trial_events import fold_trial_events
from ._apply_actions import apply_actions, check_actions, churn_step, complete
from ._notify import flush_batched_notifications, notify
from ._setup_dispatch import setup_dispatch
from ._submit_trials import submit_trials


def _job_label(t: dict) -> str:
    return f"{t['job']['name']}[{t['job']['index']}]"


def relaunch(ctx: DispatchContext, gone: set[str]) -> None:
    """Request the vanished trials again, or record as `failed` (lost)
    those that are out of retries.

    A killed attempt does not count against `trial_maxretry`.

    Parameters
    ----------
    ctx : DispatchContext
        The dispatch ticking.
    gone : set of str
        The `trial_uuid` of each trial whose job is gone or was killed.
    """
    if not gone:
        return
    trials = ctx.read_trials()  # re-read: a result may have landed since
    vanished = {
        t["trial_uuid"]: t
        for t in trials
        if t["trial_uuid"] in gone and t["status"] in ("requested", "killed")
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
        ctx.log(
            "screendoor: %s lost: job %s vanished %d times",
            uid[:8],
            _job_label(t),
            t["retries"] + 1,
        )
        ctx.write_trial_payload(
            {
                "event": "failed",
                "trial_uuid": uid,
                "attempt": t["attempt"],
                "task_id": t["task_id"],
            }
        )
    submit_trials(ctx, entries, len(trials))


def _record_churn_error(
    ctx: DispatchContext, streak: int, e: Exception
) -> None:
    tb = traceback.format_exc()
    logging.error("screendoor: churn raised (%d in a row):\n%s", streak, tb)
    ctx.write_dispatch_telemetry(
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
        complete(ctx, "failed", reason=reason)
        notify(ctx, "failure", "dispatch failed: churn keeps raising")


def tick(ctx: DispatchContext) -> None:
    """Run one daemon pass over one open dispatch.

    The pass sets the dispatch up if need be; polls its unsettled trials
    and relaunches those whose jobs are gone; then, while
    `how_unblock_churn` allows and churn keeps writing memos, calls churn
    and carries out its actions. It ends by recording a `ticked` event.

    Parameters
    ----------
    ctx : DispatchContext
        The dispatch to tick.
    """
    if not ctx.is_setup:
        setup_dispatch(ctx)
    trials = ctx.read_trials()
    in_progress = [t for t in trials if t["status"] == "requested"]
    gone = ctx.call_hook("how_poke", in_progress) if in_progress else ()
    killed = {t["trial_uuid"] for t in trials if t["status"] == "killed"}
    relaunch(ctx, set(gone) | killed)
    throttled = not ctx.call_hook("how_throttle_churn")

    streak = ctx.churn_error_streak
    while ctx.completed is None:
        submissions = ctx.read_trial_submissions()
        payloads = ctx.read_trial_payloads()
        if not ctx.call_hook("how_unblock_churn", submissions, payloads):
            break  # outstanding trials: churn waits for a later tick
        memo = ctx.read_churn_memo()
        try:  # only churn's own errors count against churn_maxretry
            actions = check_actions(
                ctx.churn(ctx.record, submissions, payloads, memo)
            )
        except Exception as e:
            streak += 1
            _record_churn_error(ctx, streak, e)
            break
        streak = 0
        if throttled:  # keep notifications and succeed / fail only
            actions = [
                a for a in actions if a["action"] not in ("launch", "memo")
            ]
        trials = fold_trial_events(submissions + payloads)
        step = churn_step(memo, submissions)
        if not apply_actions(ctx, actions, trials, memo, step):
            break  # no memo written: nothing new for churn this tick
    flush_batched_notifications(ctx)
    ctx.churn_error_streak = streak
    ctx.write_dispatch_telemetry(
        {
            "event": "ticked",
            "churn_error_streak": streak,
            "throttled": throttled,
        },
    )
