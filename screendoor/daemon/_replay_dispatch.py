import os
import random

from ..auxlib._DispatchContext import load_dispatches
from ..auxlib._canonical_json import canonical_json
from ..auxlib._fold_trial_events import fold_trial_events
from ..auxlib._make_trial_uuid import make_trial_uuid
from ..rng._step_seed import step_seed


def replay_dispatch(
    run_dir: str, *, assay: str | None = None, file=None
) -> list:
    """Re-run churn at every recorded step with the recorded seeds.

    With ``assay``, replay that assay expression instead of the recorded
    one. Prints a line per step and returns the per-step reports.
    """
    run_dir = os.path.abspath(run_dir)
    ctxs = load_dispatches(os.path.dirname(run_dir))
    ctx = next((c for c in ctxs if c.run_dir == run_dir), None)
    if ctx is None:
        raise LookupError(f"no dispatch with run dir {run_dir}")
    if assay is not None:
        ctx.record = {**ctx.record, "assay": assay}
    trial_events = ctx.hook("how_read_payload")(ctx, raw=True)
    memo_events = ctx.hook("how_read_memo")(ctx, raw=True)

    steps: dict = {}  # step seed -> what that churn call recorded
    for e in trial_events + memo_events:
        if "step_seed" not in e:
            continue  # only first requests and memos carry one
        step = steps.setdefault(
            e["step_seed"], {"ts": e["ts"], "keys": [], "memo": []}
        )
        step["ts"] = min(step["ts"], e["ts"])
        if e["event"] == "memo":
            step["memo"].append(e["data"])
        else:
            step["keys"].append(e["key"])

    reports = []
    for seed, step in sorted(steps.items(), key=lambda kv: kv[1]["ts"]):
        before = [e for e in trial_events if e["ts"] < step["ts"]]
        trials = fold_trial_events(before)
        memo = [e["data"] for e in memo_events if e["ts"] < step["ts"]]
        expected_seed = step_seed(ctx.seed, len(memo), len(trials))
        actions = ctx.churn(
            ctx.record, trials, memo, rng=random.Random(expected_seed)
        )
        known = {t["trial_uuid"] for t in trials}
        keys = [
            t["key"]
            for a in actions
            if a["action"] == "launch"
            for t in a["kwargs"]["trials"]
            if make_trial_uuid(ctx.dispatch_uuid, t["key"]) not in known
        ]
        memos = [a["kwargs"]["data"] for a in actions if a["action"] == "memo"]
        match = (
            str(expected_seed) == seed
            and sorted(map(canonical_json, keys))
            == sorted(map(canonical_json, step["keys"]))
            and memos == step["memo"]
        )
        reports.append(
            {
                "ts": step["ts"],
                "step_seed": seed,
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
