import functools
import json
import os
import re

from ._eval_hook import eval_hook, make_eval_namespace
from ._fold_trial_events import fold_trial_events
from ._now_iso import parse_iso

# labels a dispatch carries, stamped on every record written for it
NAMES = (
    "meta_project",
    "meta_experiment",
    "meta_treatment",
    "meta_user",
    "meta_attempt",
)

# also stamped on every record, but an integer: seeds the churn decorator
# scd.churn.seed_global_rngs; submit_dispatch draws one if absent
SEED_NAME = "meta_seed"

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
FILES = (
    "trial_submissions",
    "trial_payloads",
    "trial_telemetry",
    "memo",
    "notify",
)

HOOK_DEFAULTS = {
    "how_launch": "scd.orch.slurm.launch()",
    "how_poke": "scd.orch.slurm.poke()",
    "how_kill": "scd.orch.slurm.kill()",
    "how_throttle": "lambda *args, **kwargs: True",
    "how_setup": "scd.record.appendjsonl.setup()",
    **{f"how_notify_{lv}": "scd.notify.log.notify()" for lv in LEVELS},
    **{f"how_read_{f}": f"scd.record.appendjsonl.read_{f}()" for f in FILES},
    **{f"how_write_{f}": f"scd.record.appendjsonl.write_{f}()" for f in FILES},
    "how_prep_trial_payloads": "scd.record.appendjsonl.prep_trial_payloads()",
    "how_unblock_churn": "scd.unblock.all_trials_ready",
    "how_cleanup_success": "lambda *args, **kwargs: ("
    "scd.cleanup.tar(*args, **kwargs), scd.cleanup.clear(*args, **kwargs))",
    "how_cleanup_failure": "lambda *args, **kwargs: None",
}

# the daemon's own hooks, which belong to no dispatch: set in screendoor.json
WORKDIR_HOOK_DEFAULTS = {
    **{
        f"how_{op}_dispatch_{f}": f"scd.record.appendjsonl.{op}_dispatch_{f}()"
        for op in ("read", "write")
        for f in ("submissions", "payloads")
    },
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
        self.run_dir = os.path.join(
            self.workdir, run_dir_name(record, submitted_ts)
        )
        self.wdhooks = wdhooks or WorkdirHooks(workdir)
        # stamped on every record written for this dispatch
        self.labels = {
            "dispatch_uuid": self.dispatch_uuid,
            **{name: self.record[name] for name in NAMES},
            SEED_NAME: self.record[SEED_NAME],
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

    def write_dispatch_payload(self, record: dict) -> dict:
        """Record one thing the daemon did with this dispatch."""
        record = {**self.labels, **record}
        return self.wdhooks.write_dispatch_payloads(self.workdir, record)

    def read_trial_submissions(self) -> list:
        return self.hook("how_read_trial_submissions")(self)

    def read_trial_payloads(self) -> list:
        return self.hook("how_read_trial_payloads")(self)

    def read_trial_events(self) -> list:
        """Every trial event, submissions then payloads, unfolded."""
        return self.read_trial_submissions() + self.read_trial_payloads()

    def read_trials(self) -> list:
        """One dict per trial, folded from submissions and payloads."""
        return fold_trial_events(self.read_trial_events())

    def write_trial_submission(self, record: dict) -> dict:
        return self.hook("how_write_trial_submissions")(self, record)

    def write_trial_payload(self, record: dict) -> dict:
        return self.hook("how_write_trial_payloads")(self, record)

    def log(self, msg: str, *args) -> None:
        self.wdhooks.log_info(msg % args)


def fold_dispatch_events(
    workdir: str,
    submissions: list[dict],
    payloads: list[dict],
    wdhooks: WorkdirHooks | None = None,
) -> list[DispatchContext]:
    """Fold dispatch submissions and payloads into one DispatchContext each.

    Each ``submitted`` submission makes a dispatch; the payloads (setup,
    ticked, churn_error, killed, resumed, closed) give its state.
    """
    ctxs: dict[str, DispatchContext] = {}
    for ev in submissions:
        if ev["event"] == "submitted" and ev["dispatch_uuid"] not in ctxs:
            ctxs[ev["dispatch_uuid"]] = DispatchContext(
                workdir, ev["dispatch"], ev["ts"], wdhooks
            )
    for ev in sorted(payloads, key=lambda e: parse_iso(e["ts"])):
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
    submissions = wdhooks.read_dispatch_submissions(wdhooks.workdir)
    payloads = wdhooks.read_dispatch_payloads(wdhooks.workdir)
    return fold_dispatch_events(workdir, submissions, payloads, wdhooks)
