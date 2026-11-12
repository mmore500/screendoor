import os
import typing

from ..auxlib._DispatchContext import load_dispatches
from ..auxlib._canonical_json import canonical_json
from ..auxlib._fold_trial_events import fold_trial_events
from ._apply_actions import check_actions, churn_step, plan_actions


def replay_dispatch(
    run_dir: str,
    *,
    assay: str | None = None,
    file: typing.TextIO | None = None,
) -> list[dict]:
    """Re-run churn at every recorded step, from the state it saw then.

    A step is the churn call that made some trial submissions or memos;
    each records its ``churn_step``. Churn is pure, or seeds itself from
    that state with scd.churn.seed_global_rngs, so a replay should match.

    With ``assay``, replay that assay expression instead of the recorded
    one. Prints a line per step and returns the per-step reports.

    Parameters
    ----------
    run_dir : str
        The dispatch's run directory.
    assay : str or None, default None
        An assay expression to replay in place of the recorded one.
    file : TextIO or None, default None
        Where to print; None for stdout.

    Returns
    -------
    list of dict
        One per step, oldest first: ``ts``, ``churn_step``, ``match``,
        ``recorded_launches`` and ``replayed_launches``.

    Raises
    ------
    LookupError
        If no dispatch has ``run_dir``.
    """
    run_dir = os.path.abspath(run_dir)
    # run dirs are <dispatchdir>/project=.../date=...
    ctxs = load_dispatches(os.path.dirname(os.path.dirname(run_dir)))
    ctx = next((c for c in ctxs if c.run_dir == run_dir), None)
    if ctx is None:
        raise LookupError(f"no dispatch with run dir {run_dir}")
    if assay is not None:
        ctx.record = {**ctx.record, "assay": assay}
    submissions = ctx.read_trial_submissions()
    payloads = ctx.read_trial_payloads()
    memo_events = ctx.read_churn_memo_events()

    steps: dict = {}  # churn step -> what that churn call recorded
    for e in submissions + memo_events:
        if "churn_step" not in e:
            continue
        step = steps.setdefault(
            e["churn_step"], {"ts": e["ts"], "keys": [], "memo": []}
        )
        step["ts"] = min(step["ts"], e["ts"])
        if e["event"] == "memo":
            step["memo"].append(e["data"])
        else:
            step["keys"].append(e["key"])

    reports = []
    for key, step in sorted(steps.items(), key=lambda kv: kv[1]["ts"]):
        subs = [e for e in submissions if e["ts"] < step["ts"]]
        pays = [e for e in payloads if e["ts"] < step["ts"]]
        trials = fold_trial_events(subs + pays)
        memo = [e["data"] for e in memo_events if e["ts"] < step["ts"]]
        actions = check_actions(ctx.churn(ctx.record, subs, pays, memo))
        requests, memos = plan_actions(ctx, actions, trials)
        keys = [t["key"] for t in requests.values()]
        match = (
            churn_step(memo, subs) == key
            and sorted(map(canonical_json, keys))
            == sorted(map(canonical_json, step["keys"]))
            and memos == step["memo"]
        )
        reports.append(
            {
                "ts": step["ts"],
                "churn_step": key,
                "match": match,
                "recorded_launches": len(step["keys"]),
                "replayed_launches": len(keys),
            }
        )
        print(
            f"{step['ts']} {'match   ' if match else 'MISMATCH'} "
            f"launches {len(step['keys'])}->{len(keys)} "
            f"memos {len(step['memo'])}->{len(memos)}",
            file=file,
        )
    mismatched = sum(not r["match"] for r in reports)
    print(f"{len(reports)} steps replayed, {mismatched} mismatched", file=file)
    return reports
