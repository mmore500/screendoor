import functools
import json
import os
import re
import typing

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

# the daemon's own hooks, which belong to no dispatch: dispatch_hooks.json must
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
    """The dispatchdir's dispatch_hooks.json is missing, incomplete or
    wrong."""


def missing_hooks(names: typing.Iterable[str], supplied: dict) -> list[str]:
    """The hooks in ``names`` that ``supplied`` does not set.

    Parameters
    ----------
    names : iterable of str
        The hook names required.
    supplied : dict
        The settings given.

    Returns
    -------
    list of str
        The missing names, in order.
    """
    return [name for name in names if name not in supplied]


def _slug(value: typing.Any) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", str(value)).strip("-") or "-"


def run_dir_name(record: dict, submitted_ts: str) -> str:
    """``project=<p>/date=<YYYY-MM-DD>+what=<experiment>%<treatment>%<seed>
    +redo=<redo>``, from the dispatch's labels and submission date.

    Parameters
    ----------
    record : dict
        The dispatch record; labels other than ``meta_seed`` default.
    submitted_ts : str
        When it was submitted, as ISO-8601.

    Returns
    -------
    str
        The run directory, relative to the dispatchdir.
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
    """Daemon-level hooks, from the dispatchdir's ``dispatch_hooks.json``.

    The file must set every name in DISPATCHDIR_HOOK_NAMES. Each hook is
    called with ``hook_ctx`` first, except ``how_log_info``, which gets
    only a message.

    Parameters
    ----------
    dispatchdir : str
        The dispatchdir.

    Attributes
    ----------
    dispatchdir : str
        The dispatchdir, absolute.

    Raises
    ------
    DispatchdirConfigError
        If ``dispatch_hooks.json`` is missing, misses a hook or has unknown
        keys.
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
        self._hooks = {
            name: eval_hook(cfg[name], namespace)
            for name in DISPATCHDIR_HOOK_NAMES
        }

    @property
    def hook_ctx(self) -> dict:
        """What the hooks get as ``ctx``: ``{"dispatchdir"}``."""
        return {"dispatchdir": self.dispatchdir}

    def hook(self, name: str) -> typing.Callable[..., typing.Any]:
        """Hook ``name``, as its expression evaluated.

        Parameters
        ----------
        name : str
            A name in DISPATCHDIR_HOOK_NAMES.

        Returns
        -------
        Callable
            The hook.
        """
        return self._hooks[name]

    def read_dispatch_submissions(self) -> list[dict]:
        """Read the dispatchdir's dispatch submissions.

        Returns
        -------
        list of dict
            The records, from how_read_dispatch_submissions.
        """
        return self._hooks["how_read_dispatch_submissions"](self.hook_ctx)

    def read_dispatch_payloads(self) -> list[dict]:
        """Read the dispatchdir's dispatch payloads.

        Returns
        -------
        list of dict
            The records, from how_read_dispatch_payloads.
        """
        return self._hooks["how_read_dispatch_payloads"](self.hook_ctx)

    def read_dispatch_telemetry(self) -> list[dict]:
        """Read the dispatchdir's dispatch telemetry.

        Returns
        -------
        list of dict
            The records, from how_read_dispatch_telemetry.
        """
        return self._hooks["how_read_dispatch_telemetry"](self.hook_ctx)

    def write_dispatch_submissions(self, record: dict) -> dict:
        """Store ``record`` with how_write_dispatch_submissions.

        Parameters
        ----------
        record : dict
            A dispatch submission event.

        Returns
        -------
        dict
            The record, as stored.
        """
        hook = self._hooks["how_write_dispatch_submissions"]
        return hook(self.hook_ctx, record)

    def write_dispatch_payloads(self, record: dict) -> dict:
        """Store ``record`` with how_write_dispatch_payloads.

        Parameters
        ----------
        record : dict
            A dispatch payload event.

        Returns
        -------
        dict
            The record, as stored.
        """
        return self._hooks["how_write_dispatch_payloads"](
            self.hook_ctx, record
        )

    def write_dispatch_telemetry(self, record: dict) -> dict:
        """Store ``record`` with how_write_dispatch_telemetry.

        Parameters
        ----------
        record : dict
            A dispatch telemetry event.

        Returns
        -------
        dict
            The record, as stored.
        """
        hook = self._hooks["how_write_dispatch_telemetry"]
        return hook(self.hook_ctx, record)

    def log_info(self, message: str) -> None:
        """Log ``message`` with how_log_info.

        Parameters
        ----------
        message : str
            The message.
        """
        self._hooks["how_log_info"](message)


class DispatchContext:
    """One dispatch: its record, run directory and lazily evaluated hooks.

    The lifecycle attributes, ``is_setup`` on, are folded from the dispatch
    events by fold_dispatch_events.

    Parameters
    ----------
    dispatchdir : str
        The dispatchdir.
    record : dict
        The dispatch record, as submitted.
    submitted_ts : str
        When it was submitted, as ISO-8601.
    ddhooks : DispatchdirHooks or None, default None
        The dispatchdir's hooks; None loads them from ``dispatchdir``.

    Attributes
    ----------
    dispatchdir : str
        The dispatchdir, absolute.
    record : dict
        The dispatch record, with DEFAULTS filled in.
    dispatch_uuid : str
        The dispatch's uuid.
    run_dir : str
        The dispatch's run directory, absolute.
    ddhooks : DispatchdirHooks
        The dispatchdir's hooks.
    labels : dict
        Stamped on every record written for this dispatch.
    is_setup : bool
        Whether how_setup has run.
    completed : dict or None
        The ``completed`` event, once there is one.
    killed : bool
        Paused by kill_dispatch, until resumed.
    churn_error_streak : int
        Churn calls in a row that raised.
    churn_error : str or None
        Repr of the error, while the streak lasts.
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

    @property
    def hook_ctx(self) -> dict:
        """What the dispatch's hooks get as ``ctx``: ``{"dispatchdir",
        "run_dir", "dispatch_uuid", "dispatch"}``, the last the dispatch
        record."""
        return {
            "dispatchdir": self.dispatchdir,
            "run_dir": self.run_dir,
            "dispatch_uuid": self.dispatch_uuid,
            "dispatch": self.record,
        }

    @functools.cached_property
    def namespace(self) -> dict:
        """The namespace hooks are evaluated in, made by ``eval_context``."""
        return make_eval_namespace(self.record["eval_context"])

    @functools.cached_property
    def churn(
        self,
    ) -> typing.Callable[
        [dict, list[dict], list[dict], list[typing.Any]], list[dict]
    ]:
        """The assay's churn function, from the ``assay`` expression."""
        assay = eval_hook(self.record["assay"], self.namespace)
        return getattr(assay, "churn", assay)

    def hook_expr(self, name: str) -> str:
        """The expression the dispatch sets for hook ``name``.

        Parameters
        ----------
        name : str
            A name in HOOK_NAMES.

        Returns
        -------
        str
            The hook expression.

        Raises
        ------
        MissingHookError
            If the dispatch does not set ``name``.
        """
        if name not in self.record:
            raise MissingHookError(
                f"dispatch {self.dispatch_uuid} does not set {name}"
            )
        return self.record[name]

    def hook(self, name: str) -> typing.Callable[..., typing.Any]:
        """Hook ``name``, evaluated on first use.

        Parameters
        ----------
        name : str
            A name in HOOK_NAMES.

        Returns
        -------
        Callable
            The hook, as its expression evaluates.

        Raises
        ------
        MissingHookError
            If the dispatch does not set ``name``.
        """
        if name not in self._hooks:
            self._hooks[name] = eval_hook(self.hook_expr(name), self.namespace)
        return self._hooks[name]

    def call_hook(self, name: str, *args: typing.Any) -> typing.Any:
        """Call hook ``name`` with ``hook_ctx`` and ``args``.

        Parameters
        ----------
        name : str
            A name in HOOK_NAMES.
        *args
            The hook's arguments after ``ctx``.

        Returns
        -------
        object
            What the hook returns.
        """
        return self.hook(name)(self.hook_ctx, *args)

    def trial_dir(self, trial_uuid: str) -> str:
        """A trial's directory: ``<run_dir>/trials/<trial_uuid>``.

        Parameters
        ----------
        trial_uuid : str
            The trial.

        Returns
        -------
        str
            The directory's path.
        """
        return os.path.join(self.run_dir, "trials", trial_uuid)

    def write_dispatch_payload(self, record: dict) -> dict:
        """Record how this dispatch ended: its ``completed`` event.

        Parameters
        ----------
        record : dict
            The ``completed`` event.

        Returns
        -------
        dict
            The record, labelled, as stored.
        """
        record = {**self.labels, **record}
        return self.ddhooks.write_dispatch_payloads(record)

    def write_dispatch_telemetry(self, record: dict) -> dict:
        """Record something that happened to this dispatch along the way.

        Parameters
        ----------
        record : dict
            The telemetry event.

        Returns
        -------
        dict
            The record, labelled, as stored.
        """
        record = {**self.labels, **record}
        return self.ddhooks.write_dispatch_telemetry(record)

    # every record goes through these, which stamp the dispatch's labels;
    # the storage hooks just store it

    def read_trial_submissions(self) -> list[dict]:
        """Read the dispatch's trial submissions.

        Returns
        -------
        list of dict
            The records, from how_read_trial_submissions.
        """
        return self.call_hook("how_read_trial_submissions")

    def read_trial_payloads(self) -> list[dict]:
        """Read the dispatch's trial payloads.

        Returns
        -------
        list of dict
            The records, from how_read_trial_payloads.
        """
        return self.call_hook("how_read_trial_payloads")

    def read_trial_telemetry(self) -> list[dict]:
        """Read the dispatch's trial telemetry.

        Returns
        -------
        list of dict
            The records, from how_read_trial_telemetry.
        """
        return self.call_hook("how_read_trial_telemetry")

    def read_trials(self) -> list[dict]:
        """One dict per trial, folded from submissions and payloads.

        Returns
        -------
        list of dict
            The folded trials, as from scd.churn.fold_trials.
        """
        subs, pays = self.read_trial_submissions(), self.read_trial_payloads()
        return fold_trial_events(subs + pays)

    def read_churn_memo_events(self) -> list[dict]:
        """Memo events, oldest first, one per index (a crash can leave a
        step's memo written twice).

        Returns
        -------
        list of dict
            The first event for each ``index``, by index.
        """
        by_index: dict = {}
        events = self.call_hook("how_read_churn_memo")
        for e in sorted(events, key=lambda e: (e["index"], e["ts"])):
            by_index.setdefault(e["index"], e)
        return list(by_index.values())

    def read_churn_memo(self) -> list[typing.Any]:
        """What churn sees as ``memo``: the memo payloads, oldest first.

        Returns
        -------
        list
            Each memo event's ``data``.
        """
        return [e["data"] for e in self.read_churn_memo_events()]

    def read_churn_notify(self) -> list[dict]:
        """Read the dispatch's notification records.

        Returns
        -------
        list of dict
            The records, from how_read_churn_notify.
        """
        return self.call_hook("how_read_churn_notify")

    def _write(self, hook: str, record: dict) -> dict:
        return self.call_hook(hook, {**self.labels, **record})

    def write_trial_submission(self, record: dict) -> dict:
        """Label ``record`` and store it with how_write_trial_submissions.

        Parameters
        ----------
        record : dict
            A trial submission event.

        Returns
        -------
        dict
            The record, labelled, as stored.
        """
        return self._write("how_write_trial_submissions", record)

    def write_trial_payload(self, record: dict) -> dict:
        """Label ``record`` and store it with how_write_trial_payloads.

        Parameters
        ----------
        record : dict
            A trial payload event.

        Returns
        -------
        dict
            The record, labelled, as stored.
        """
        return self._write("how_write_trial_payloads", record)

    def write_trial_telemetry(self, record: dict) -> dict:
        """Label ``record`` and store it with how_write_trial_telemetry.

        Parameters
        ----------
        record : dict
            A trial telemetry event.

        Returns
        -------
        dict
            The record, labelled, as stored.
        """
        return self._write("how_write_trial_telemetry", record)

    def write_churn_memo(self, record: dict) -> dict:
        """Label ``record`` and store it with how_write_churn_memo.

        Parameters
        ----------
        record : dict
            A memo event.

        Returns
        -------
        dict
            The record, labelled, as stored.
        """
        return self._write("how_write_churn_memo", record)

    def write_churn_notify(self, record: dict) -> dict:
        """Label ``record`` and store it with how_write_churn_notify.

        Parameters
        ----------
        record : dict
            A notification event.

        Returns
        -------
        dict
            The record, labelled, as stored.
        """
        return self._write("how_write_churn_notify", record)

    def log(self, msg: str, *args: typing.Any) -> None:
        """Log ``msg % args`` with the dispatchdir's how_log_info.

        Parameters
        ----------
        msg : str
            A %-format string.
        *args
            Its arguments.
        """
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

    Parameters
    ----------
    dispatchdir : str
        The dispatchdir.
    submissions : list of dict
        Dispatch submission records.
    payloads : list of dict
        Dispatch payload records.
    telemetry : list of dict
        Dispatch telemetry records.
    ddhooks : DispatchdirHooks or None, default None
        The dispatchdir's hooks; None loads them from ``dispatchdir``.

    Returns
    -------
    list of DispatchContext
        One per dispatch, in order of submission.
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
    """Every dispatch in ``dispatchdir``, from its dispatch records.

    Parameters
    ----------
    dispatchdir : str
        The dispatchdir.

    Returns
    -------
    list of DispatchContext
        One per dispatch, in order of submission.
    """
    ddhooks = DispatchdirHooks(dispatchdir)
    submissions = ddhooks.read_dispatch_submissions()
    payloads = ddhooks.read_dispatch_payloads()
    telemetry = ddhooks.read_dispatch_telemetry()
    return fold_dispatch_events(
        dispatchdir, submissions, payloads, telemetry, ddhooks
    )


def load_dispatch(dispatchdir: str, dispatch_uuid: str) -> DispatchContext:
    """The dispatch ``dispatch_uuid`` in ``dispatchdir``.

    Parameters
    ----------
    dispatchdir : str
        The dispatchdir.
    dispatch_uuid : str
        The dispatch's uuid.

    Returns
    -------
    DispatchContext
        The dispatch, from its dispatch records.

    Raises
    ------
    LookupError
        If there is no such dispatch.
    """
    for ctx in load_dispatches(dispatchdir):
        if ctx.dispatch_uuid == dispatch_uuid:
            return ctx
    raise LookupError(f"no dispatch {dispatch_uuid} in {dispatchdir}")
