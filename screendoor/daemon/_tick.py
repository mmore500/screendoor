import logging
import random
import traceback

from ..auxlib._DispatchContext import LEVELS
from ..rng._step_seed import step_seed
from ._apply_actions import apply_actions, close
from ._launch_trials import launch_entries, make_launch_id
from ._notify import flush_batched_notifications, notify

IN_PROGRESS = ("launched", "running")


def relaunch(ctx, gone: set) -> None:
    """Request vanished trials again, or record them ``failed: lost``.

    A killed attempt does not count against ``trial_maxretry``.
    """
    if not gone:
        return
    write = ctx.hook("how_write_payload")
    vanished = {  # re-read: a result may have landed since the poke
        t["trial_uuid"]: t
        for t in ctx.hook("how_read_payload")(ctx)
        if t["trial_uuid"] in gone and t["status"] in (*IN_PROGRESS, "killed")
    }
    entries = []
    for uid, t in vanished.items():
        free = t["status"] == "killed"
        if free or t["retries"] < ctx.record["trial_maxretry"]:
            entries.append({"trial_uuid": uid, "attempt": t["attempt"] + 1})
            continue
        write(
            ctx,
            {
                "event": "failed",
                "trial_uuid": uid,
                "attempt": t["attempt"],
                "kind": "lost",
                "exit_code": None,
                "channels": {},
                "stderr_tail": f"job {t['job_id']} vanished "
                f"{t['retries'] + 1} times",
            },
        )
    launch_id = make_launch_id(entries)
    for e in entries:
        t = vanished[e["trial_uuid"]]
        ctx.log(
            "screendoor: relaunching %s (job %s vanished), attempt %d",
            t["trial_uuid"][:8],
            t["job_id"],
            e["attempt"],
        )
        write(
            ctx,
            {
                "event": "requested",
                **e,
                "task_id": t["task_id"],
                "key": t["key"],
                "request": t["request"],
                "launch_id": launch_id,
            },
        )
    launch_entries(ctx, entries, launch_id)


def reconcile(ctx) -> None:
    """Requested but never launched: adopt the job if it exists, or launch."""
    by_launch: dict = {}
    for t in ctx.hook("how_read_payload")(ctx):
        if t["status"] == "requested":
            by_launch.setdefault(t["launch_id"], []).append(
                {"trial_uuid": t["trial_uuid"], "attempt": t["attempt"]}
            )
    adopt = (
        getattr(ctx.hook("how_launch"), "adopt", None) if by_launch else None
    )
    unlaunched = []
    for launch_id, entries in by_launch.items():
        jobs = adopt(ctx, launch_id, entries) if adopt and launch_id else {}
        for e in entries:
            job = jobs.get((e["trial_uuid"], e["attempt"]))
            if job is None:
                unlaunched.append(e)
                continue
            ctx.log(
                "screendoor: adopting job %s for %s", job, e["trial_uuid"][:8]
            )
            ctx.hook("how_write_payload")(
                ctx,
                {
                    "event": "launched",
                    **e,
                    "job_id": job,
                    "launch_id": launch_id,
                },
            )
    launch_entries(ctx, unlaunched, make_launch_id(unlaunched))


def tick(ctx) -> None:
    """One daemon pass over one open dispatch."""
    if not ctx.is_setup:
        ctx.hook("how_setup")(ctx)
    trials = ctx.hook("how_read_payload")(ctx)
    in_progress = [t for t in trials if t["status"] in IN_PROGRESS]
    gone = ctx.hook("how_poke")(ctx, in_progress) if in_progress else ()
    killed = {t["trial_uuid"] for t in trials if t["status"] == "killed"}
    relaunch(ctx, set(gone) | killed)
    reconcile(ctx)
    throttled = not ctx.hook("how_throttle")(ctx)

    streak = ctx.churn_error_streak
    while ctx.closed is None:
        trials = ctx.hook("how_read_payload")(ctx)
        memo = ctx.hook("how_read_memo")(ctx)
        seed = step_seed(ctx.seed, len(memo), len(trials))
        try:
            actions = ctx.churn(
                ctx.record, trials, memo, rng=random.Random(seed)
            )
            if throttled:  # keep notifications and succeed / fail only
                actions = [
                    a
                    for a in actions
                    if a.get("action") not in ("launch", "memo")
                ]
            wrote_memo = apply_actions(ctx, actions, trials, memo, seed)
        except Exception as e:
            streak += 1
            tb = traceback.format_exc()
            logging.error(
                "screendoor: churn raised (%d in a row):\n%s", streak, tb
            )
            ctx.write_dispatch(
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
    ctx.write_dispatch(
        {
            "event": "ticked",
            "churn_error_streak": streak,
            "throttled": throttled,
        },
    )
