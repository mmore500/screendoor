import logging
import typing

from ..auxlib._DispatchContext import DispatchContext
from ..auxlib._make_trial_uuid import make_trial_uuid
from ..auxlib._tally_trials import tally_trials
from ..churn._ORDER import ORDER
from ._notify import notify
from ._submit_trials import submit_trials


def churn_step(memo: list[typing.Any], trial_submissions: list[dict]) -> str:
    """Name the churn call that sees `memo` and `trial_submissions`, as
    `"<memos>:<trial submissions>"`.

    Trial submissions and memos record the step of the call that made
    them, which is how `replay_dispatch` finds that call.

    Parameters
    ----------
    memo : list
        The memo payloads churn sees.
    trial_submissions : list of dict
        The trial submissions churn sees.

    Returns
    -------
    str
        The step.
    """
    return f"{len(memo)}:{len(trial_submissions)}"


def complete(ctx: DispatchContext, outcome: str, **fields: typing.Any) -> None:
    """Record that the dispatch completed, with a tally of its trials, then
    run its cleanup hook.

    A cleanup hook that raises is logged and recorded as a `cleanup_error`
    event; the dispatch stays completed.

    Parameters
    ----------
    ctx : DispatchContext
        The dispatch completing.
    outcome : str
        `succeeded` or `failed`.
    **fields
        Recorded with the outcome: `summary` or `reason`.
    """
    trials = ctx.read_trials()
    ctx.completed = {
        "outcome": outcome,
        **fields,
        "tally": tally_trials(trials),
    }
    ctx.write_dispatch_payload({"event": "completed", **ctx.completed})
    which = "success" if outcome == "succeeded" else "failure"
    try:
        ctx.call_hook(f"how_cleanup_{which}", ctx.completed)
    except Exception as e:
        logging.exception("screendoor: how_cleanup_%s raised", which)
        ctx.write_dispatch_telemetry(
            {"event": "cleanup_error", "hook": which, "error": repr(e)},
        )


def check_actions(actions: typing.Any) -> list[dict]:
    """Check that churn returned a list of actions, and sort them into the
    order they apply.

    Parameters
    ----------
    actions : Any
        What churn returned.

    Returns
    -------
    list of dict
        The actions, sorted by `ORDER`.

    Raises
    ------
    TypeError
        If `actions` is not a list.
    ValueError
        If an item is not a dict whose `action` is in `ORDER`.
    """
    if not isinstance(actions, list):
        raise TypeError(f"churn must return a list, got {type(actions)}")
    for a in actions:
        if not isinstance(a, dict) or a.get("action") not in ORDER:
            raise ValueError(f"not an action: {a!r}")
    return sorted(actions, key=lambda a: ORDER.index(a["action"]))


def plan_actions(
    ctx: DispatchContext, actions: list[dict], trials: list[dict]
) -> tuple[dict[str, dict], list[typing.Any]]:
    """Work out the trials to submit and the memos to record from churn's
    actions.

    A request for a trial that already exists, or that is asked for twice,
    is dropped with a warning.

    Parameters
    ----------
    ctx : DispatchContext
        The dispatch churn ran for.
    actions : list of dict
        Churn's checked actions.
    trials : list of dict
        The folded trials churn saw.

    Returns
    -------
    requests : dict of {str: dict}
        The requested trials by `trial_uuid`, in request order.
    memos : list
        The memo payloads.
    """
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
    memos = [a["kwargs"]["data"] for a in actions if a["action"] == "memo"]
    return requests, memos


def apply_actions(
    ctx: DispatchContext,
    actions: list[dict],
    trials: list[dict],
    memo: list[typing.Any],
    step: str,
) -> bool:
    """Carry out churn's checked actions.

    Parameters
    ----------
    ctx : DispatchContext
        The dispatch churn ran for.
    actions : list of dict
        Churn's checked actions.
    trials : list of dict
        The folded trials churn saw.
    memo : list
        The memo payloads churn saw.
    step : str
        The `churn_step` of the call.

    Returns
    -------
    bool
        Whether a memo was written, in which case churn runs again this
        tick.
    """
    requests, memos = plan_actions(ctx, actions, trials)
    # task ids count trials in request order: 0, 1, 2, ...
    submit_trials(
        ctx,
        [
            {
                "trial_uuid": uid,
                "attempt": 0,
                "task_id": task_id,
                "key": t["key"],
                "request": {
                    k: t[k] for k in ("cmd", "env", "weight") if k in t
                },
                "churn_step": step,
            }
            for task_id, (uid, t) in enumerate(requests.items(), len(trials))
        ],
        len(trials) + len(requests),
    )

    for index, data in enumerate(memos, start=len(memo)):
        ctx.write_churn_memo(
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
        elif kind == "succeed" and ctx.completed is None:
            complete(ctx, "succeeded", summary=kw["summary"])
            notify(ctx, "success", "dispatch succeeded", kw)
        elif kind == "fail" and ctx.completed is None:
            complete(ctx, "failed", reason=kw["reason"])
            notify(ctx, "failure", f"dispatch failed: {kw['reason']}", kw)
    return bool(memos)
