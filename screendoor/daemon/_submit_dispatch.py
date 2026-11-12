import json
import secrets
import uuid

from ..auxlib._DispatchContext import (
    HOOK_NAMES,
    NAMES,
    SEED_NAME,
    MissingHookError,
    WorkdirHooks,
    missing_hooks,
)
from ..auxlib._next_cron_firing import parse_cron

SETTINGS = {
    *NAMES,
    SEED_NAME,
    "assay",
    "assay_kwargs",
    "schedule",
    "trial_batchsize",
    "trial_batch_timeout",
    "trial_maxretry",
    "churn_maxretry",
    "eval_context",
    "dispatch_uuid",
}


def validate_dispatch(obj: dict) -> None:
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
        if not isinstance(value, int) or value < least:
            raise ValueError(f"{key} must be an integer of at least {least}")


def submit_dispatch(obj: dict, workdir: str) -> str:
    """Record a new dispatch; return its dispatch_uuid.

    Fills in ``dispatch_uuid``, ``meta_seed`` (32 random bits from the
    operating system) and, as ``"default"``, any absent ``meta_*`` label.
    """
    obj = json.loads(json.dumps(obj))  # a deep copy that must be JSON
    validate_dispatch(obj)
    obj.setdefault("dispatch_uuid", str(uuid.uuid4()))
    for key in NAMES:
        obj.setdefault(key, "default")
    obj.setdefault(SEED_NAME, secrets.randbits(32))
    wdhooks = WorkdirHooks(workdir)
    wdhooks.write_dispatch_submissions(
        wdhooks.workdir,
        {
            "event": "submitted",
            "dispatch_uuid": obj["dispatch_uuid"],
            **{key: obj[key] for key in (*NAMES, SEED_NAME)},
            "dispatch": obj,
        },
    )
    return obj["dispatch_uuid"]
