import logging

from ..auxlib._make_trial_uuid import make_trial_uuid
from ..auxlib._tally_trials import tally_trials
from ..churn._ORDER import ORDER
from ._launch_trials import submit_trials
from ._notify import notify


def churn_step(memo: list, trial_submissions: list) -> str:
    """Which churn call this is: ``"<memos>:<trial submissions>"`` seen."""
    return f"{len(memo)}:{len(trial_submissions)}"


def close(ctx, outcome: str, **fields) -> None:
    """Record the dispatch closed, with a tally of its trials so far, then
    call how_cleanup_success or how_cleanup_failure.

    A cleanup that raises is logged and recorded as ``cleanup_error``; the
    dispatch stays closed.
    """
    trials = ctx.read_trials()
    ctx.closed = {"outcome": outcome, **fields, "tally": tally_trials(trials)}
    ctx.write_dispatch_payload(
        {"event": "closed", **ctx.closed},
    )
    which = "success" if outcome == "succeeded" else "failure"
    try:
        ctx.hook(f"how_cleanup_{which}")(ctx, ctx.closed)
    except Exception as e:
        logging.exception("screendoor: how_cleanup_%s raised", which)
        ctx.write_dispatch_payload(
            {"event": "cleanup_error", "hook": which, "error": repr(e)},
        )


def apply_actions(
    ctx, actions: list, trials: list, memo: list, step: str
) -> bool:
    """Carry out churn's actions; return whether a memo was written.

    ``trials`` are the folded trials churn saw. Trial submissions and
    memos record ``step``, the churn_step of the call, which is how
    replay_dispatch finds the call that made them.
    """
    if not isinstance(actions, list):
        raise TypeError(f"churn must return a list, got {type(actions)}")
    for a in actions:
        if not isinstance(a, dict) or a.get("action") not in ORDER:
            raise ValueError(f"not an action: {a!r}")
    actions = sorted(actions, key=lambda a: ORDER.index(a["action"]))

    known = {t["trial_uuid"] for t in trials}
    requests = {}
    for a in actions:
        for t in a["kwargs"]["trials"] if a["action"] == "launch" else ():
            uid = make_trial_uuid(ctx.dispatch_uuid, t["key"])
            if uid in known or uid in requests:
                logging.warning(
                    "screendoor: dropping duplicate trial request key=%s",
                    t["key"],
                )
            else:
                requests[uid] = t
    # task ids count trials in request order: 0, 1, 2, ...
    submit_trials(
        ctx,
        [
            {
                "trial_uuid": uid,
                "attempt": 0,
                "task_id": task_id,
                "key": t["key"],
                "request": {"cmd": t["cmd"], "env": t["env"]},
                "churn_step": step,
            }
            for task_id, (uid, t) in enumerate(requests.items(), len(trials))
        ],
    )

    memos = [a["kwargs"]["data"] for a in actions if a["action"] == "memo"]
    for index, data in enumerate(memos, start=len(memo)):
        ctx.hook("how_write_memo")(
            ctx,
            {
                "event": "memo",
                "index": index,
                "data": data,
                "churn_step": step,
            },
        )

    for a in actions:
        kind, kw = a["action"], a["kwargs"]
        if kind == "progress":
            message = f"{kw['done']}/{kw['total']} {kw.get('message', '')}"
            notify(ctx, "progress", message.strip(), kw)
        elif kind == "eta":
            notify(ctx, "eta", f"eta {kw['eta']}", kw)
        elif kind in ("warning", "anomaly"):
            notify(ctx, kind, kw["message"], kw)
        elif kind == "succeed" and ctx.closed is None:
            close(ctx, "succeeded", summary=kw["summary"])
            notify(ctx, "success", "dispatch succeeded", kw)
        elif kind == "fail" and ctx.closed is None:
            close(ctx, "failed", reason=kw["reason"])
            notify(ctx, "failure", f"dispatch failed: {kw['reason']}", kw)
    return bool(memos)
