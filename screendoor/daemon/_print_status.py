from ..auxlib._DispatchContext import NAMES, SEED_NAME, load_dispatches
from ..auxlib._tally_trials import tally_trials
from ._next_firing import next_firing


def _state(ctx) -> str:
    if ctx.completed:
        return ctx.completed["outcome"]
    return "killed" if ctx.killed else "open"


def dispatch_status(dispatchdir: str, *, max_failures: int = 3) -> list:
    """One dict per dispatch: its labels and state, trial counts and
    tally, when it last ticked and is next due, whether it is throttled or
    churn is raising, and the exit codes of the first ``max_failures``
    failed trials (None: lost)."""
    rows = []
    for ctx in load_dispatches(dispatchdir):
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
            "failed": len(failed),
            "failures": [
                {k: t[k] for k in ("trial_uuid", "key", "exit_code")}
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
    return rows


def _lines(row: dict) -> list:
    counts = ", ".join(f"{k}={v}" for k, v in row["trials"].items())
    extras = ("retries", "kills", "warnings")
    tally = ", ".join(f"{k} {row['tally'][k]}" for k in extras)
    meta = ", ".join(
        f"{name.removeprefix('meta_')}={row[name]}"
        for name in (*NAMES, SEED_NAME)
    )
    lines = [
        f"{row['dispatch_uuid'][:8]} {row['state']:9} {row['assay']}",
        f"    meta: {meta}",
        f"    trials: {counts or 'none'} ({tally})",
    ]
    for f in row["failures"]:
        how = "lost" if f["exit_code"] is None else f"exit {f['exit_code']}"
        lines.append(
            f"    failed {f['trial_uuid'][:8]} key={f['key']}: {how}"[:200]
        )
    if row["failed"] > len(row["failures"]):
        lines.append(
            f"    ... and {row['failed'] - len(row['failures'])} more"
        )
    if row["state"] == "open":
        note = ", throttled" if row["throttled"] else ""
        lines.append(
            f"    last tick: {row['last_tick'] or 'never'}{note}; "
            f"next: {row['next_tick']}"
        )
    elif row["state"] == "killed":
        lines.append("    killed: resume with resume_dispatch")
    if row["churn_error_streak"]:
        lines.append(
            f"    churn raised {row['churn_error_streak']} ticks in a row: "
            f"{row['churn_error']}"[:200]
        )
    if "completed" in row:
        lines.append(f"    completed: {row['completed']}"[:500])
    lines.append(f"    run_dir: {row['run_dir']}")
    return lines


def print_status(
    dispatchdir: str, *, file=None, max_failures: int = 3
) -> list:
    """Print dispatch_status as text; return its rows."""
    rows = dispatch_status(dispatchdir, max_failures=max_failures)
    for row in rows:
        print(*_lines(row), sep="\n", file=file)
    return rows
