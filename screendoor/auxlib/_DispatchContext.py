import functools
import json
import os
import re

from ._eval_hook import eval_hook, make_eval_namespace
from ._now_iso import parse_iso

# labels a dispatch carries, stamped on every record written for it
NAMES = (
    "meta_project",
    "meta_experiment",
    "meta_treatment",
    "meta_user",
    "meta_attempt",
)

DEFAULTS = {
    **dict.fromkeys(NAMES, "default"),
    "assay_kwargs": {},
    "trial_batchsize": 1,
    "trial_batch_timeout": None,
    "trial_maxretry": 3,
    "churn_maxretry": 5,
    "eval_context": None,
}

LEVELS = ("progress", "eta", "success", "failure", "warning", "anomaly")
FILES = ("payload", "memo", "notify", "telemetry")

HOOK_DEFAULTS = {
    "how_launch": "scd.orchestrate.slurm.launch()",
    "how_poke": "scd.orchestrate.slurm.poke()",
    "how_kill": "scd.orchestrate.slurm.kill()",
    "how_throttle": "scd.orchestrate.null.throttle()",
    "how_setup": "scd.record.jsonl.setup()",
    **{f"how_notify_{lv}": "scd.notify.log.notify()" for lv in LEVELS},
    **{f"how_read_{f}": f"scd.record.jsonl.read_{f}()" for f in FILES},
    **{f"how_write_{f}": f"scd.record.jsonl.write_{f}()" for f in FILES},
    "how_prep_payload": "scd.record.jsonl.prep_payload()",
}

# the daemon's own hooks, which belong to no dispatch: set in screendoor.json
WORKDIR_HOOK_DEFAULTS = {
    "how_read_dispatch": "scd.record.jsonl.read_dispatch()",
    "how_write_dispatch": "scd.record.jsonl.write_dispatch()",
    "how_log_info": "logging.info",
    "how_notify_liveness": "scd.notify.null.notify()",
    "how_notify_termination": "scd.notify.log.notify()",
}


def run_dir_name(record: dict, submitted_ts: str) -> str:
    assay = record["assay"]
    match = re.match(r"(?:scd|screendoor)\.assaylib\.(\w+)", assay)
    short = match[1] if match else assay.rstrip("()").split(".")[-1]
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", short).strip("-") or "assay"
    date = parse_iso(submitted_ts).date().isoformat()
    uid = record["dispatch_uuid"].replace("-", "")[:8]
    return f"assay={slug}+date={date}+uuid={uid}+what=screendoor"


class WorkdirHooks:
    """Daemon-level hooks, from the optional ``screendoor.json``.

    Each ``how_<name>`` hook becomes the attribute ``<name>``.
    """

    dispatch_uuid = "daemon"  # how notifiers label the daemon's own messages

    def __init__(self, workdir: str):
        self.workdir = os.path.abspath(workdir)
        try:
            path = os.path.join(self.workdir, "screendoor.json")
            with open(path, encoding="utf-8") as fh:
                cfg = json.load(fh)
        except FileNotFoundError:
            cfg = {}
        namespace = make_eval_namespace(cfg.get("eval_context"))
        for name, default in WORKDIR_HOOK_DEFAULTS.items():
            hook = eval_hook(cfg.get(name, default), namespace)
            setattr(self, name.removeprefix("how_"), hook)


class DispatchContext:
    """One dispatch: its record, run directory and lazily evaluated hooks."""

    def __init__(
        self,
        workdir: str,
        record: dict,
        submitted_ts: str,
        wdhooks: WorkdirHooks | None = None,
    ):
        self.workdir = os.path.abspath(workdir)
        self.record = {**DEFAULTS, **record}
        self.dispatch_uuid = record["dispatch_uuid"]
        self.seed = int(record["seed"])
        self.run_dir = os.path.join(
            self.workdir, run_dir_name(record, submitted_ts)
        )
        self.wdhooks = wdhooks or WorkdirHooks(workdir)
        # stamped on every record written for this dispatch
        self.labels = {
            "dispatch_uuid": self.dispatch_uuid,
            **{name: self.record[name] for name in NAMES},
        }
        self._hooks: dict = {}
        # lifecycle, folded from the dispatch events
        self.is_setup = False
        self.closed = None  # the `closed` event, once there is one
        self.killed = False  # paused by kill_dispatch, until resumed
        self.churn_error_streak = 0
        self.churn_error = None  # repr of the error, while the streak lasts
        self.last_tick = None
        self.throttled = False  # on the last tick

    @property
    def active(self) -> bool:
        """Whether the daemon should tick this dispatch."""
        return self.closed is None and not self.killed

    @functools.cached_property
    def namespace(self) -> dict:
        return make_eval_namespace(self.record["eval_context"])

    @functools.cached_property
    def churn(self):
        assay = eval_hook(self.record["assay"], self.namespace)
        return getattr(assay, "churn", assay)

    def hook_expr(self, name: str) -> str:
        return self.record.get(name, HOOK_DEFAULTS[name])

    def hook(self, name: str):
        if name not in self._hooks:
            self._hooks[name] = eval_hook(self.hook_expr(name), self.namespace)
        return self._hooks[name]

    def trial_dir(self, trial_uuid: str) -> str:
        return os.path.join(self.run_dir, "trials", trial_uuid)

    def write_dispatch(self, record: dict) -> dict:
        """Append one of this dispatch's events to the dispatch records."""
        record = {**self.labels, **record}
        return self.wdhooks.write_dispatch(self.workdir, record)

    def log(self, msg: str, *args) -> None:
        self.wdhooks.log_info(msg % args)


def fold_dispatch_events(
    workdir: str, events: list[dict], wdhooks: WorkdirHooks | None = None
) -> list[DispatchContext]:
    """Fold screendoor-dispatch.jsonl into one DispatchContext each."""
    ctxs: dict[str, DispatchContext] = {}
    for ev in events:
        if ev["event"] == "submitted" and ev["dispatch_uuid"] not in ctxs:
            ctxs[ev["dispatch_uuid"]] = DispatchContext(
                workdir, ev["dispatch"], ev["ts"], wdhooks
            )
    for ev in sorted(events, key=lambda e: parse_iso(e["ts"])):
        ctx = ctxs.get(ev.get("dispatch_uuid"))
        if ctx is None:
            continue
        if ev["event"] == "setup":
            ctx.is_setup = True
        elif ev["event"] == "closed":
            ctx.closed = ctx.closed or ev
        elif ev["event"] in ("killed", "resumed"):
            ctx.killed = ev["event"] == "killed"
        elif ev["event"] == "churn_error":
            ctx.churn_error_streak = ev["streak"]
            ctx.churn_error = ev["error"]
        elif ev["event"] == "ticked":
            ctx.churn_error_streak = ev["churn_error_streak"]
            if not ctx.churn_error_streak:
                ctx.churn_error = None
            ctx.last_tick = parse_iso(ev["ts"])
            ctx.throttled = ev["throttled"]
    return list(ctxs.values())


def load_dispatches(workdir: str) -> list[DispatchContext]:
    wdhooks = WorkdirHooks(workdir)
    events = wdhooks.read_dispatch(wdhooks.workdir)
    return fold_dispatch_events(workdir, events, wdhooks)
