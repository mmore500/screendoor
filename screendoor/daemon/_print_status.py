import typing

from ..auxlib._DispatchContext import (
    LABEL_NAMES,
    SEED_NAME,
    DispatchContext,
    load_dispatches,
)
from ..auxlib._tally_trials import tally_trials
from ._next_firing import next_firing


def _state(ctx: DispatchContext) -> str:
    if ctx.completed:
        return ctx.completed["outcome"]
    return "killed" if ctx.killed else "open"


def dispatch_status(dispatchdir: str, *, max_failures: int = 3) -> list[dict]:
    """Summarize every dispatch in `dispatchdir`, one dict each.

    Each dict carries the dispatch's labels and state, its trial counts and
    tally, when it last ticked and is next due, whether churn is throttled
    or raising, and the first `max_failures` failed trials with their exit
    codes (None for a lost trial).

    Parameters
    ----------
    dispatchdir : str
        Path of the dispatchdir.
    max_failures : int, default 3
        How many failed trials to list per dispatch.

    Returns
    -------
    list of dict
        One JSON-serializable row per dispatch, in order of submission.
    """
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


def _lines(row: dict) -> list[str]:
    counts = ", ".join(f"{k}={v}" for k, v in row["trials"].items())
    extras = ("retries", "kills", "warnings")
    tally = ", ".join(f"{k} {row['tally'][k]}" for k in extras)
    meta = ", ".join(
        f"{name.removeprefix('meta_')}={row[name]}"
        for name in (*LABEL_NAMES, SEED_NAME)
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
    dispatchdir: str,
    *,
    file: typing.TextIO | None = None,
    max_failures: int = 3,
) -> list[dict]:
    """Print the rows of `dispatch_status` as text and return them.

    Parameters
    ----------
    dispatchdir : str
        Path of the dispatchdir.
    file : TextIO or None, default None
        Where to print; None prints to stdout.
    max_failures : int, default 3
        How many failed trials to list per dispatch.

    Returns
    -------
    list of dict
        The rows of `dispatch_status`.
    """
    rows = dispatch_status(dispatchdir, max_failures=max_failures)
    for row in rows:
        print(*_lines(row), sep="\n", file=file)
    return rows
