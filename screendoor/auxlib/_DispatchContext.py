import functools
import json
import os
import re
import typing

from ._eval_hook import eval_hook, make_eval_namespace
from ._fold_trial_events import fold_trial_events
from ._now_iso import parse_iso

# labels a dispatch carries, stamped on every record written for it
LABEL_NAMES = (
    "meta_project",
    "meta_experiment",
    "meta_treatment",
    "meta_user",
    "meta_redo",
)
# also stamped on every record; seeds scd.churn.seed_global_rngs
SEED_NAME = "meta_seed"

DEFAULTS = {
    **dict.fromkeys(LABEL_NAMES, "default"),
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

# a dispatch must set each of these to an expression; none has a default
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

# the daemon's own hooks, set by the dispatchdir's dispatch_hooks.json
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
    """Raised when a dispatch leaves a hook unset.

    screendoor supplies no default for any hook.
    """


class DispatchdirConfigError(ValueError):
    """Raised when a dispatchdir's `dispatch_hooks.json` is missing,
    leaves a hook unset or has unknown keys."""


def _slug(value: typing.Any) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", str(value)).strip("-") or "-"


def run_dir_name(record: dict, submitted_ts: str) -> str:
    """Build the run directory name of a dispatch from its labels and
    submission date.

    Parameters
    ----------
    record : dict
        The dispatch record; absent labels take their defaults.
    submitted_ts : str
        When the dispatch was submitted, as an ISO-8601 timestamp.

    Returns
    -------
    str
        A path relative to the dispatchdir, of the form `project=<p>/
        date=<YYYY-MM-DD>+what=<experiment>%<treatment>%<seed>+redo=<r>`.
    """
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
    """Hooks of the daemon itself, read from a dispatchdir's
    `dispatch_hooks.json`.

    The file must set every name in `DISPATCHDIR_HOOK_NAMES`. Each hook is
    called with `hook_ctx` as its first argument, except `how_log_info`,
    which gets only a message.

    Parameters
    ----------
    dispatchdir : str
        Path of the dispatchdir.

    Raises
    ------
    DispatchdirConfigError
        If `dispatch_hooks.json` is missing, leaves a hook unset or has
        unknown keys.
    """

    def __init__(self, dispatchdir: str) -> None:
        self.dispatchdir = os.path.abspath(dispatchdir)
        path = os.path.join(self.dispatchdir, "dispatch_hooks.json")
        try:
            with open(path, encoding="utf-8") as fh:
                cfg = json.load(fh)
        except FileNotFoundError:
            raise DispatchdirConfigError(
                f"{path} is missing; it must set "
                + ", ".join(DISPATCHDIR_HOOK_NAMES)
            ) from None
        missing = [name for name in DISPATCHDIR_HOOK_NAMES if name not in cfg]
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
        self._hooks = {
            name: eval_hook(cfg[name], namespace)
            for name in DISPATCHDIR_HOOK_NAMES
        }

    @property
    def hook_ctx(self) -> dict:
        """Context passed to each hook: `{"dispatchdir": ...}`."""
        return {"dispatchdir": self.dispatchdir}

    def hook(self, name: str) -> typing.Callable[..., typing.Any]:
        """Return the hook `name`, a name in `DISPATCHDIR_HOOK_NAMES`."""
        return self._hooks[name]

    def read_dispatch_submissions(self) -> list[dict]:
        """Read the dispatchdir's dispatch submission records."""
        return self.hook("how_read_dispatch_submissions")(self.hook_ctx)

    def read_dispatch_payloads(self) -> list[dict]:
        """Read the dispatchdir's dispatch payload records."""
        return self.hook("how_read_dispatch_payloads")(self.hook_ctx)

    def read_dispatch_telemetry(self) -> list[dict]:
        """Read the dispatchdir's dispatch telemetry records."""
        return self.hook("how_read_dispatch_telemetry")(self.hook_ctx)

    def write_dispatch_submission(self, record: dict) -> dict:
        """Store a dispatch submission record; return it as stored."""
        hook = self.hook("how_write_dispatch_submissions")
        return hook(self.hook_ctx, record)

    def write_dispatch_payload(self, record: dict) -> dict:
        """Store a dispatch payload record; return it as stored."""
        return self.hook("how_write_dispatch_payloads")(self.hook_ctx, record)

    def write_dispatch_telemetry(self, record: dict) -> dict:
        """Store a dispatch telemetry record; return it as stored."""
        return self.hook("how_write_dispatch_telemetry")(self.hook_ctx, record)

    def log_info(self, message: str) -> None:
        """Log `message` through `how_log_info`."""
        self.hook("how_log_info")(message)


class DispatchContext:
    """One dispatch: its record, run directory, lifecycle and hooks.

    Hooks are evaluated from the dispatch's expressions on first use. The
    lifecycle attributes are folded from the dispatch's payload and
    telemetry records by `load_dispatches`.

    Parameters
    ----------
    dispatchdir : str
        Path of the dispatchdir.
    record : dict
        The dispatch record, as submitted.
    submitted_ts : str
        When the dispatch was submitted, as an ISO-8601 timestamp.
    ddhooks : DispatchdirHooks or None, default None
        The dispatchdir's hooks; loaded from `dispatchdir` if None.

    Attributes
    ----------
    dispatchdir : str
        Absolute path of the dispatchdir.
    record : dict
        The dispatch record, with `DEFAULTS` filled in.
    dispatch_uuid : str
        The dispatch's uuid.
    run_dir : str
        Absolute path of the dispatch's run directory.
    ddhooks : DispatchdirHooks
        The dispatchdir's hooks.
    labels : dict
        Fields stamped on every record written for the dispatch.
    is_setup : bool
        Whether `how_setup` has run.
    completed : dict or None
        The `completed` event, once the dispatch has one.
    killed : bool
        Whether the dispatch is paused by `kill_dispatch`.
    churn_error_streak : int
        How many churn calls in a row have raised.
    churn_error : str or None
        Repr of the latest error, while the streak lasts.
    last_tick : datetime.datetime or None
        When the dispatch was last ticked.
    throttled : bool
        Whether churn was throttled on the last tick.
    """

    def __init__(
        self,
        dispatchdir: str,
        record: dict,
        submitted_ts: str,
        ddhooks: DispatchdirHooks | None = None,
    ) -> None:
        self.dispatchdir = os.path.abspath(dispatchdir)
        self.record = {**DEFAULTS, **record}
        self.dispatch_uuid = record["dispatch_uuid"]
        self.run_dir = os.path.join(
            self.dispatchdir, run_dir_name(record, submitted_ts)
        )
        self.ddhooks = ddhooks or DispatchdirHooks(dispatchdir)
        self.labels = {
            "dispatch_uuid": self.dispatch_uuid,
            **{name: self.record[name] for name in (*LABEL_NAMES, SEED_NAME)},
        }
        self._hooks: dict = {}
        self.is_setup = False
        self.completed = None
        self.killed = False
        self.churn_error_streak = 0
        self.churn_error = None
        self.last_tick = None
        self.throttled = False

    @property
    def active(self) -> bool:
        """Whether the daemon should tick this dispatch: it is neither
        completed nor killed."""
        return self.completed is None and not self.killed

    @property
    def hook_ctx(self) -> dict:
        """Context passed to the dispatch's hooks: `dispatchdir`, `run_dir`,
        `dispatch_uuid` and the `dispatch` record."""
        return {
            "dispatchdir": self.dispatchdir,
            "run_dir": self.run_dir,
            "dispatch_uuid": self.dispatch_uuid,
            "dispatch": self.record,
        }

    @functools.cached_property
    def namespace(self) -> dict:
        """Namespace the dispatch's hook expressions are evaluated in, built
        by its `eval_context`."""
        return make_eval_namespace(self.record["eval_context"])

    @functools.cached_property
    def churn(
        self,
    ) -> typing.Callable[
        [dict, list[dict], list[dict], list[typing.Any]], list[dict]
    ]:
        """The assay's churn function, from the dispatch's `assay`
        expression."""
        assay = eval_hook(self.record["assay"], self.namespace)
        return getattr(assay, "churn", assay)

    def hook(self, name: str) -> typing.Callable[..., typing.Any]:
        """Return the hook `name`, evaluating its expression on first use.

        Parameters
        ----------
        name : str
            A name in `HOOK_NAMES`.

        Returns
        -------
        Callable
            The hook.
        """
        if name not in self._hooks:
            self._hooks[name] = eval_hook(self.record[name], self.namespace)
        return self._hooks[name]

    def call_hook(self, name: str, *args: typing.Any) -> typing.Any:
        """Call the hook `name` with `hook_ctx` followed by `args`."""
        return self.hook(name)(self.hook_ctx, *args)

    def trial_dir(self, trial_uuid: str) -> str:
        """Return the directory of trial `trial_uuid`:
        `<run_dir>/trials/<trial_uuid>`."""
        return os.path.join(self.run_dir, "trials", trial_uuid)

    def read_trial_submissions(self) -> list[dict]:
        """Read the dispatch's trial submission records."""
        return self.call_hook("how_read_trial_submissions")

    def read_trial_payloads(self) -> list[dict]:
        """Read the dispatch's trial payload records."""
        return self.call_hook("how_read_trial_payloads")

    def read_trial_telemetry(self) -> list[dict]:
        """Read the dispatch's trial telemetry records."""
        return self.call_hook("how_read_trial_telemetry")

    def read_trials(self) -> list[dict]:
        """Fold the dispatch's trial submissions and payloads into one dict
        per trial, as `scd.churn.fold_trials` does."""
        subs, pays = self.read_trial_submissions(), self.read_trial_payloads()
        return fold_trial_events(subs + pays)

    def read_churn_memo_events(self) -> list[dict]:
        """Read the dispatch's memo events, oldest first.

        Only the first event at each `index` is kept: a crash can record one
        step's memo twice.
        """
        by_index: dict = {}
        events = self.call_hook("how_read_churn_memo")
        for e in sorted(events, key=lambda e: (e["index"], e["ts"])):
            by_index.setdefault(e["index"], e)
        return list(by_index.values())

    def read_churn_memo(self) -> list[typing.Any]:
        """Read the memo payloads churn sees as `memo`, oldest first."""
        return [e["data"] for e in self.read_churn_memo_events()]

    def read_churn_notify(self) -> list[dict]:
        """Read the dispatch's notification records."""
        return self.call_hook("how_read_churn_notify")

    def _write(self, hook: str, record: dict) -> dict:
        return self.call_hook(hook, {**self.labels, **record})

    def write_trial_submission(self, record: dict) -> dict:
        """Stamp a trial submission record with the dispatch's labels and
        store it; return it as stored."""
        return self._write("how_write_trial_submissions", record)

    def write_trial_payload(self, record: dict) -> dict:
        """Stamp a trial payload record with the dispatch's labels and store
        it; return it as stored."""
        return self._write("how_write_trial_payloads", record)

    def write_trial_telemetry(self, record: dict) -> dict:
        """Stamp a trial telemetry record with the dispatch's labels and
        store it; return it as stored."""
        return self._write("how_write_trial_telemetry", record)

    def write_churn_memo(self, record: dict) -> dict:
        """Stamp a memo record with the dispatch's labels and store it;
        return it as stored."""
        return self._write("how_write_churn_memo", record)

    def write_churn_notify(self, record: dict) -> dict:
        """Stamp a notification record with the dispatch's labels and store
        it; return it as stored."""
        return self._write("how_write_churn_notify", record)

    def write_dispatch_payload(self, record: dict) -> dict:
        """Stamp the dispatch's `completed` event with its labels and store
        it through the dispatchdir's hooks; return it as stored."""
        return self.ddhooks.write_dispatch_payload({**self.labels, **record})

    def write_dispatch_telemetry(self, record: dict) -> dict:
        """Stamp a dispatch telemetry event with the dispatch's labels and
        store it through the dispatchdir's hooks; return it as stored."""
        return self.ddhooks.write_dispatch_telemetry({**self.labels, **record})

    def log(self, msg: str, *args: typing.Any) -> None:
        """Log `msg % args` through the dispatchdir's `how_log_info`."""
        self.ddhooks.log_info(msg % args)


def load_dispatches(dispatchdir: str) -> list[DispatchContext]:
    """Load every dispatch in `dispatchdir` from its dispatch records.

    Each `submitted` submission makes a dispatch. Its payload, `completed`,
    says how it ended; its telemetry (`setup`, `ticked`, `churn_error`,
    `killed`, `resumed`) gives its state along the way.

    Parameters
    ----------
    dispatchdir : str
        Path of the dispatchdir.

    Returns
    -------
    list of DispatchContext
        One per dispatch, in order of submission.

    Raises
    ------
    DispatchdirConfigError
        If the dispatchdir's `dispatch_hooks.json` is missing or wrong.
    """
    ddhooks = DispatchdirHooks(dispatchdir)
    ctxs: dict[str, DispatchContext] = {}
    for ev in ddhooks.read_dispatch_submissions():
        if ev["event"] == "submitted" and ev["dispatch_uuid"] not in ctxs:
            ctxs[ev["dispatch_uuid"]] = DispatchContext(
                dispatchdir, ev["dispatch"], ev["ts"], ddhooks
            )
    events = [
        *ddhooks.read_dispatch_payloads(),
        *ddhooks.read_dispatch_telemetry(),
    ]
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


def load_dispatch(dispatchdir: str, dispatch_uuid: str) -> DispatchContext:
    """Load the dispatch `dispatch_uuid` from `dispatchdir`.

    Parameters
    ----------
    dispatchdir : str
        Path of the dispatchdir.
    dispatch_uuid : str
        The dispatch's uuid.

    Returns
    -------
    DispatchContext
        The dispatch, as `load_dispatches` loads it.

    Raises
    ------
    LookupError
        If `dispatchdir` has no such dispatch.
    """
    for ctx in load_dispatches(dispatchdir):
        if ctx.dispatch_uuid == dispatch_uuid:
            return ctx
    raise LookupError(f"no dispatch {dispatch_uuid} in {dispatchdir}")
