from ..auxlib._DispatchContext import NAMES, SEED_NAME, load_dispatches
from ..auxlib._tally_trials import tally_trials
from ._run_tick_once import next_firing


def _state(ctx) -> str:
    if ctx.completed:
        return ctx.completed["outcome"]
    return "killed" if ctx.killed else "open"


def print_status(workdir: str, *, file=None, max_failures: int = 3) -> list:
    """Print each dispatch's state; return the same as a list of dicts.

    Shows the trial counts and tally, when the dispatch last ticked and is
    next due, whether it is throttled or churn is raising, and how the
    first ``max_failures`` failed trials ended.
    """
    rows = []
    for ctx in load_dispatches(workdir):
        trials = ctx.read_trials() if ctx.is_setup else []
        statuses = sorted({t["status"] for t in trials})
        failed = [t for t in trials if t["status"] == "failed"]
        row = {
            **ctx.labels,
            "assay": ctx.record["assay"],
            "state": _state(ctx),
            "trials": {
                s: sum(t["status"] == s for t in trials) for s in statuses
            },
            "tally": tally_trials(trials),
            "failures": [
                {"trial_uuid": t["trial_uuid"], "key": t["key"], **t["error"]}
                for t in failed[:max_failures]
            ],
            "run_dir": ctx.run_dir,
            "last_tick": ctx.last_tick and ctx.last_tick.isoformat(),
            "next_tick": next_firing(ctx).isoformat() if ctx.active else None,
            "throttled": ctx.throttled,
            "churn_error_streak": ctx.churn_error_streak,
            "churn_error": ctx.churn_error,
        }
        if ctx.completed:
            row["completed"] = {
                k: ctx.completed[k]
                for k in ("summary", "reason")
                if k in ctx.completed
            }
        rows.append(row)

        counts = ", ".join(f"{k}={v}" for k, v in row["trials"].items())
        extras = ("no_result", "retries", "kills", "warnings", "malformed")
        tally = ", ".join(f"{k} {row['tally'][k]}" for k in extras)
        lines = [
            f"{ctx.dispatch_uuid[:8]} {row['state']:9} {row['assay']}",
            "    meta: "
            + ", ".join(
                f"{name.removeprefix('meta_')}={ctx.record[name]}"
                for name in (*NAMES, SEED_NAME)
            ),
            f"    trials: {counts or 'none'} ({tally})",
        ]
        for f in row["failures"]:
            tail = (f["stderr_tail"] or "").strip().splitlines()[-1:]
            lines.append(
                f"    failed {f['trial_uuid'][:8]} key={f['key']}: "
                f"{f['kind']}, exit {f['exit_code']}: {' '.join(tail)}"[:200]
            )
        if len(failed) > max_failures:
            lines.append(f"    ... and {len(failed) - max_failures} more")
        if ctx.active:
            note = ", throttled" if ctx.throttled else ""
            lines.append(
                f"    last tick: {row['last_tick'] or 'never'}{note}; "
                f"next: {row['next_tick']}"
            )
        elif ctx.killed and not ctx.completed:
            lines.append("    killed: resume with resume_dispatch")
        if ctx.churn_error_streak:
            lines.append(
                f"    churn raised {ctx.churn_error_streak} ticks in a row: "
                f"{ctx.churn_error}"[:200]
            )
        if ctx.completed:
            lines.append(f"    completed: {row['completed']}"[:500])
        lines.append(f"    run_dir: {ctx.run_dir}")
        print(*lines, sep="\n", file=file)
    return rows
