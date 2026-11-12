import logging

from ..act._ORDER import ORDER
from ..auxlib._make_trial_uuid import make_trial_uuid
from ..auxlib._tally_trials import tally_trials
from ._launch_trials import launch_entries, make_launch_id
from ._notify import notify


def close(ctx, outcome: str, **fields) -> None:
    """Record the dispatch closed, with a tally of its trials so far."""
    trials = ctx.hook("how_read_payload")(ctx)
    ctx.closed = {"outcome": outcome, **fields, "tally": tally_trials(trials)}
    ctx.write_dispatch(
        {"event": "closed", **ctx.closed},
    )


def apply_actions(
    ctx, actions: list, trials: list, memo: list, step_seed: int
) -> bool:
    """Carry out churn's actions; return whether a memo was written."""
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
    if requests:
        entries = [{"trial_uuid": uid, "attempt": 0} for uid in requests]
        launch_id = make_launch_id(entries)
        # task ids count trials in request order: 0, 1, 2, ...
        for task_id, (uid, t) in enumerate(requests.items(), len(trials)):
            ctx.hook("how_write_payload")(
                ctx,
                {
                    "event": "requested",
                    "trial_uuid": uid,
                    "attempt": 0,
                    "task_id": task_id,
                    "key": t["key"],
                    "request": {"cmd": t["cmd"], "env": t["env"]},
                    "step_seed": str(step_seed),
                    "launch_id": launch_id,
                },
            )
        launch_entries(ctx, entries, launch_id)

    memos = [a["kwargs"]["data"] for a in actions if a["action"] == "memo"]
    for index, data in enumerate(memos, start=len(memo)):
        ctx.hook("how_write_memo")(
            ctx,
            {
                "event": "memo",
                "index": index,
                "data": data,
                "step_seed": str(step_seed),
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
