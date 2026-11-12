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
    "meta_redo",
)

# also stamped on every record, but an integer: seeds the churn decorator
# scd.churn.seed_global_rngs; submit_dispatch draws one if absent
SEED_NAME = "meta_seed"

DEFAULTS = {
    **dict.fromkeys(NAMES, "default"),
    "meta_redo": "0",
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
    "churn_memo",
    "churn_notify",
)

# every dispatch must set each of these to an expression: none has a default
HOOK_NAMES = (
    "how_launch",
    "how_poke",
    "how_kill",
    "how_throttle_churn",
    "how_setup",
    *(f"how_notify_{lv}" for lv in LEVELS),
    *(f"how_{op}_{f}" for f in FILES for op in ("read", "write")),
    "how_prep_trial_payloads",
    "how_unblock_churn",
    "how_cleanup_success",
    "how_cleanup_failure",
)

# the daemon's own hooks, which belong to no dispatch: screendoor.json must
# set each of these
DISPATCHDIR_HOOK_NAMES = (
    *(
        f"how_{op}_dispatch_{f}"
        for f in ("submissions", "payloads", "telemetry")
        for op in ("read", "write")
    ),
    "how_log_info",
    "how_notify_liveness",
    "how_notify_termination",
)


class MissingHookError(ValueError):
    """A hook was not supplied; screendoor has no default for any."""


class DispatchdirConfigError(ValueError):
    """The dispatchdir's screendoor.json is missing, incomplete or wrong."""


def missing_hooks(names, supplied: dict) -> list:
    return [name for name in names if name not in supplied]


def _slug(value) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", str(value)).strip("-") or "-"


def run_dir_name(record: dict, submitted_ts: str) -> str:
    """``project=<p>/date=<YYYY-MM-DD>+what=<experiment>%<treatment>%<seed>
    +redo=<redo>``, from the dispatch's labels and submission date."""
    r = {**DEFAULTS, **record}
    date = parse_iso(submitted_ts).astimezone().date().isoformat()
    what = "%".join(
        _slug(r[k]) for k in ("meta_experiment", "meta_treatment", SEED_NAME)
    )
    return os.path.join(
        f"project={_slug(r['meta_project'])}",
        f"date={date}+what={what}+redo={_slug(r['meta_redo'])}",
    )


class DispatchdirHooks:
    """Daemon-level hooks, from the dispatchdir's ``screendoor.json``.

    The file must set every name in DISPATCHDIR_HOOK_NAMES; each
    ``how_<name>`` hook becomes the attribute ``<name>``.
    """

    dispatch_uuid = "daemon"  # how notifiers label the daemon's own messages

    def __init__(self, dispatchdir: str):
        self.dispatchdir = os.path.abspath(dispatchdir)
        path = os.path.join(self.dispatchdir, "screendoor.json")
        try:
            with open(path, encoding="utf-8") as fh:
                cfg = json.load(fh)
        except FileNotFoundError:
            raise DispatchdirConfigError(
                f"{path} is missing; it must set "
                + ", ".join(DISPATCHDIR_HOOK_NAMES)
            ) from None
        missing = missing_hooks(DISPATCHDIR_HOOK_NAMES, cfg)
        if missing:
            raise DispatchdirConfigError(
                f"{path} must set " + ", ".join(missing)
            )
        unknown = sorted(set(cfg) - {*DISPATCHDIR_HOOK_NAMES, "eval_context"})
        if unknown:
            raise DispatchdirConfigError(
                f"{path} has unknown keys: {', '.join(unknown)}"
            )
        namespace = make_eval_namespace(cfg.get("eval_context"))
        for name in DISPATCHDIR_HOOK_NAMES:
            hook = eval_hook(cfg[name], namespace)
            setattr(self, name.removeprefix("how_"), hook)


class DispatchContext:
    """One dispatch: its record, run directory and lazily evaluated hooks."""

    def __init__(
        self,
        dispatchdir: str,
        record: dict,
        submitted_ts: str,
        ddhooks: DispatchdirHooks | None = None,
    ):
        self.dispatchdir = os.path.abspath(dispatchdir)
        self.record = {**DEFAULTS, **record}
        self.dispatch_uuid = record["dispatch_uuid"]
        self.run_dir = os.path.join(
            self.dispatchdir, run_dir_name(record, submitted_ts)
        )
        self.ddhooks = ddhooks or DispatchdirHooks(dispatchdir)
        # stamped on every record written for this dispatch
        self.labels = {
            "dispatch_uuid": self.dispatch_uuid,
            **{name: self.record[name] for name in NAMES},
            SEED_NAME: self.record[SEED_NAME],
        }
        self._hooks: dict = {}
        # lifecycle, folded from the dispatch events
        self.is_setup = False
        self.completed = None  # the `completed` event, once there is one
        self.killed = False  # paused by kill_dispatch, until resumed
        self.churn_error_streak = 0
        self.churn_error = None  # repr of the error, while the streak lasts
        self.last_tick = None
        self.throttled = False  # on the last tick

    @property
    def active(self) -> bool:
        """Whether the daemon should tick this dispatch."""
        return self.completed is None and not self.killed

    @functools.cached_property
    def namespace(self) -> dict:
        return make_eval_namespace(self.record["eval_context"])

    @functools.cached_property
    def churn(self):
        assay = eval_hook(self.record["assay"], self.namespace)
        return getattr(assay, "churn", assay)

    def hook_expr(self, name: str) -> str:
        if name not in self.record:
            raise MissingHookError(
                f"dispatch {self.dispatch_uuid} does not set {name}"
            )
        return self.record[name]

    def hook(self, name: str):
        if name not in self._hooks:
            self._hooks[name] = eval_hook(self.hook_expr(name), self.namespace)
        return self._hooks[name]

    def trial_dir(self, trial_uuid: str) -> str:
        return os.path.join(self.run_dir, "trials", trial_uuid)

    def write_dispatch_payload(self, record: dict) -> dict:
        """Record how this dispatch ended: its ``completed`` event."""
        record = {**self.labels, **record}
        return self.ddhooks.write_dispatch_payloads(self.ddhooks, record)

    def write_dispatch_telemetry(self, record: dict) -> dict:
        """Record something that happened to this dispatch along the way."""
        record = {**self.labels, **record}
        return self.ddhooks.write_dispatch_telemetry(self.ddhooks, record)

    # every record goes through these, which stamp the dispatch's labels;
    # the storage hooks just store it

    def read_trial_submissions(self) -> list:
        return self.hook("how_read_trial_submissions")(self)

    def read_trial_payloads(self) -> list:
        return self.hook("how_read_trial_payloads")(self)

    def read_trials(self) -> list:
        """One dict per trial, folded from submissions and payloads."""
        subs, pays = self.read_trial_submissions(), self.read_trial_payloads()
        return fold_trial_events(subs + pays)

    def read_churn_memo_events(self) -> list:
        """Memo events, oldest first, one per index (a crash can leave a
        step's memo written twice)."""
        by_index: dict = {}
        events = self.hook("how_read_churn_memo")(self)
        for e in sorted(events, key=lambda e: (e["index"], e["ts"])):
            by_index.setdefault(e["index"], e)
        return list(by_index.values())

    def read_churn_memo(self) -> list:
        """What churn sees as ``memo``: the memo payloads, oldest first."""
        return [e["data"] for e in self.read_churn_memo_events()]

    def read_churn_notify(self) -> list:
        return self.hook("how_read_churn_notify")(self)

    def _write(self, hook: str, record: dict) -> dict:
        return self.hook(hook)(self, {**self.labels, **record})

    def write_trial_submission(self, record: dict) -> dict:
        return self._write("how_write_trial_submissions", record)

    def write_trial_payload(self, record: dict) -> dict:
        return self._write("how_write_trial_payloads", record)

    def write_trial_telemetry(self, record: dict) -> dict:
        return self._write("how_write_trial_telemetry", record)

    def write_churn_memo(self, record: dict) -> dict:
        return self._write("how_write_churn_memo", record)

    def write_churn_notify(self, record: dict) -> dict:
        return self._write("how_write_churn_notify", record)

    def log(self, msg: str, *args) -> None:
        self.ddhooks.log_info(msg % args)


def fold_dispatch_events(
    dispatchdir: str,
    submissions: list[dict],
    payloads: list[dict],
    telemetry: list[dict],
    ddhooks: DispatchdirHooks | None = None,
) -> list[DispatchContext]:
    """Fold dispatch records into one DispatchContext each.

    Each ``submitted`` submission makes a dispatch. Its payload, ``completed``,
    says how it ended; its telemetry (setup, ticked, churn_error, killed,
    resumed, cleanup_error) gives its state along the way.
    """
    ctxs: dict[str, DispatchContext] = {}
    for ev in submissions:
        if ev["event"] == "submitted" and ev["dispatch_uuid"] not in ctxs:
            ctxs[ev["dispatch_uuid"]] = DispatchContext(
                dispatchdir, ev["dispatch"], ev["ts"], ddhooks
            )
    events = [*payloads, *telemetry]
    for ev in sorted(events, key=lambda e: parse_iso(e["ts"])):
        ctx = ctxs.get(ev.get("dispatch_uuid"))
        if ctx is None:
            continue
        if ev["event"] == "setup":
            ctx.is_setup = True
        elif ev["event"] == "completed":
            ctx.completed = ctx.completed or ev
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


def load_dispatches(dispatchdir: str) -> list[DispatchContext]:
    ddhooks = DispatchdirHooks(dispatchdir)
    submissions = ddhooks.read_dispatch_submissions(ddhooks)
    payloads = ddhooks.read_dispatch_payloads(ddhooks)
    telemetry = ddhooks.read_dispatch_telemetry(ddhooks)
    return fold_dispatch_events(
        dispatchdir, submissions, payloads, telemetry, ddhooks
    )
