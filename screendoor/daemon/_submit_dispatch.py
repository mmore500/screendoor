import json
import os
import secrets
import uuid

from ..auxlib._DispatchContext import (
    DEFAULTS,
    HOOK_NAMES,
    LABEL_NAMES,
    SEED_NAME,
    DispatchdirHooks,
    MissingHookError,
    load_dispatches,
    run_dir_name,
)
from ..auxlib._eval_hook import eval_hook, make_eval_namespace
from ..auxlib._next_cron_firing import parse_cron
from ..auxlib._now_iso import now_iso

SETTINGS = {*DEFAULTS, SEED_NAME, "assay", "schedule", "dispatch_uuid"}


def validate_dispatch(obj: dict) -> None:
    """Check that `obj` is a valid dispatch before it is recorded.

    Checks the dispatch's keys and their types, parses its `schedule`, and
    evaluates its `assay` and every hook expression.

    Parameters
    ----------
    obj : dict
        The dispatch, as parsed from JSON.

    Raises
    ------
    MissingHookError
        If `obj` leaves a hook unset.
    ValueError
        If `obj` is otherwise not a valid dispatch.
    """
    if not isinstance(obj, dict):
        raise ValueError("a dispatch must be a JSON object")
    for key in ("assay", "schedule"):
        if key not in obj:
            raise ValueError(f"dispatch needs {key!r}")
    parse_cron(obj["schedule"])
    missing = [name for name in HOOK_NAMES if name not in obj]
    if missing:
        raise MissingHookError("dispatch must set " + ", ".join(missing))
    for key, value in obj.items():
        if key not in SETTINGS and key not in HOOK_NAMES:
            raise ValueError(f"unknown dispatch key {key!r}")
        if key in HOOK_NAMES and not isinstance(value, str):
            raise ValueError(f"{key} must be an expression string")
    for key in LABEL_NAMES:
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
        is_int = isinstance(value, int) and not isinstance(value, bool)
        if not is_int or value < least:
            raise ValueError(f"{key} must be an integer of at least {least}")
    namespace = make_eval_namespace(obj.get("eval_context"))
    for key in ("assay", *HOOK_NAMES):
        try:
            eval_hook(obj[key], namespace)
        except Exception as e:
            raise ValueError(f"{key} {obj[key]!r} raised {e!r}") from e


def submit_dispatch(obj: dict, dispatchdir: str) -> str:
    """Record a new dispatch in `dispatchdir`.

    Fills in `dispatch_uuid`, `meta_seed` (32 random bits from the operating
    system) and any absent `meta_*` label (`"0"` for `meta_redo`,
    `"default"` for the rest). Submitting only records the dispatch; a
    daemon must be started separately to run it.

    Parameters
    ----------
    obj : dict
        The dispatch, as parsed from JSON; not modified.
    dispatchdir : str
        Path of the dispatchdir.

    Returns
    -------
    str
        The new dispatch's `dispatch_uuid`.

    Raises
    ------
    DispatchdirConfigError
        If the dispatchdir's `dispatch_hooks.json` is missing or wrong.
    ValueError
        If `obj` is not a valid dispatch, its `dispatch_uuid` is taken, or
        an open dispatch already uses its run directory.
    """
    obj = json.loads(json.dumps(obj))  # a deep copy that must be JSON
    validate_dispatch(obj)
    obj.setdefault("dispatch_uuid", str(uuid.uuid4()))
    for key in LABEL_NAMES:
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
    ddhooks.write_dispatch_submission(
        {
            "event": "submitted",
            "dispatch_uuid": obj["dispatch_uuid"],
            **{key: obj[key] for key in (*LABEL_NAMES, SEED_NAME)},
            "dispatch": obj,
        },
    )
    return obj["dispatch_uuid"]
