import json
import os
import secrets
import uuid

from ..auxlib._DispatchContext import (
    DEFAULTS,
    HOOK_NAMES,
    NAMES,
    SEED_NAME,
    DispatchdirHooks,
    MissingHookError,
    load_dispatches,
    missing_hooks,
    run_dir_name,
)
from ..auxlib._eval_hook import eval_hook, make_eval_namespace
from ..auxlib._next_cron_firing import parse_cron
from ..auxlib._now_iso import now_iso

SETTINGS = {*DEFAULTS, SEED_NAME, "assay", "schedule", "dispatch_uuid"}


def validate_dispatch(obj: dict) -> None:
    """Check a dispatch before it is recorded.

    Checks its keys and their types, its ``schedule``, and that its
    ``assay`` and every hook evaluate.

    Parameters
    ----------
    obj : dict
        The dispatch, as parsed JSON.

    Raises
    ------
    MissingHookError
        If ``obj`` does not set every hook.
    ValueError
        If ``obj`` is otherwise not a valid dispatch.
    """
    if not isinstance(obj, dict):
        raise ValueError("a dispatch must be a JSON object")
    for key in ("assay", "schedule"):
        if key not in obj:
            raise ValueError(f"dispatch needs {key!r}")
    parse_cron(obj["schedule"])
    missing = missing_hooks(HOOK_NAMES, obj)
    if missing:  # no hook has a default
        raise MissingHookError("dispatch must set " + ", ".join(missing))
    for key, value in obj.items():
        if key not in SETTINGS and key not in HOOK_NAMES:
            raise ValueError(f"unknown dispatch key {key!r}")
        if key in HOOK_NAMES and not isinstance(value, str):
            raise ValueError(f"{key} must be an expression string")
    for key in NAMES:
        if not isinstance(obj.get(key, ""), str):
            raise ValueError(f"{key} must be a string")
    if "dispatch_uuid" in obj:
        try:
            uuid.UUID(obj["dispatch_uuid"])
        except (TypeError, ValueError, AttributeError):
            raise ValueError("dispatch_uuid must be a UUID string") from None
    seed = obj.get(SEED_NAME, 0)
    if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
        raise ValueError(f"{SEED_NAME} must be a non-negative integer")
    if not isinstance(obj.get("assay_kwargs", {}), dict):
        raise ValueError("assay_kwargs must be an object")
    for key, least in (
        ("trial_batchsize", 1),
        ("trial_maxretry", 0),
        ("churn_maxretry", 0),
    ):
        value = obj.get(key, least)
        if type(value) is not int or value < least:  # no bools
            raise ValueError(f"{key} must be an integer of at least {least}")
    namespace = make_eval_namespace(obj.get("eval_context"))
    for key in ("assay", *HOOK_NAMES):
        try:
            eval_hook(obj[key], namespace)
        except Exception as e:
            raise ValueError(f"{key} {obj[key]!r} raised {e!r}") from e


def submit_dispatch(obj: dict, dispatchdir: str) -> str:
    """Record a new dispatch; return its dispatch_uuid.

    Fills in ``dispatch_uuid``, ``meta_seed`` (32 random bits from the
    operating system) and any absent ``meta_*`` label (``"0"`` for
    ``meta_redo``, ``"default"`` for the rest). Refuses a dispatch whose
    run directory an open dispatch already uses.

    Parameters
    ----------
    obj : dict
        The dispatch, as parsed JSON; not modified.
    dispatchdir : str
        The dispatchdir to record it in.

    Returns
    -------
    str
        The new dispatch's dispatch_uuid.

    Raises
    ------
    DispatchdirConfigError
        If the dispatchdir's ``screendoor.json`` is missing or wrong.
    ValueError
        If ``obj`` is not a valid dispatch, its dispatch_uuid exists, or
        an open dispatch uses its run directory.
    """
    obj = json.loads(json.dumps(obj))  # a deep copy that must be JSON
    validate_dispatch(obj)
    obj.setdefault("dispatch_uuid", str(uuid.uuid4()))
    for key in NAMES:
        obj.setdefault(key, DEFAULTS[key])
    obj.setdefault(SEED_NAME, secrets.randbits(32))
    ddhooks = DispatchdirHooks(dispatchdir)
    run_dir = os.path.join(ddhooks.dispatchdir, run_dir_name(obj, now_iso()))
    for ctx in load_dispatches(dispatchdir):
        if ctx.dispatch_uuid == obj["dispatch_uuid"]:
            raise ValueError(f"dispatch {ctx.dispatch_uuid} already exists")
        if ctx.active and ctx.run_dir == run_dir:
            raise ValueError(
                f"open dispatch {ctx.dispatch_uuid} uses {run_dir}; "
                "change meta_redo"
            )
    ddhooks.write_dispatch_submissions(
        {
            "event": "submitted",
            "dispatch_uuid": obj["dispatch_uuid"],
            **{key: obj[key] for key in (*NAMES, SEED_NAME)},
            "dispatch": obj,
        },
    )
    return obj["dispatch_uuid"]
