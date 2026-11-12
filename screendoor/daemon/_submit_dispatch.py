import json
import uuid

from ..auxlib._DispatchContext import HOOK_DEFAULTS, NAMES, WorkdirHooks
from ..auxlib._next_cron_firing import parse_cron
from ..rng._derive_seed import derive_seed

SETTINGS = {
    *NAMES,
    "assay",
    "assay_kwargs",
    "schedule",
    "seed",
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
    for key, value in obj.items():
        if key not in SETTINGS and key not in HOOK_DEFAULTS:
            raise ValueError(f"unknown dispatch key {key!r}")
        if key in HOOK_DEFAULTS and not isinstance(value, str):
            raise ValueError(f"{key} must be an expression string")
    for key in NAMES:
        if not isinstance(obj.get(key, ""), str):
            raise ValueError(f"{key} must be a string")
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

    Fills in ``dispatch_uuid``, ``seed`` and, as ``"default"``, any absent
    ``meta_*`` label.
    """
    obj = json.loads(json.dumps(obj))  # a deep copy that must be JSON
    validate_dispatch(obj)
    obj.setdefault("dispatch_uuid", str(uuid.uuid4()))
    for key in NAMES:
        obj.setdefault(key, "default")
    obj.setdefault("seed", derive_seed("dispatch", obj["dispatch_uuid"]))
    wdhooks = WorkdirHooks(workdir)
    wdhooks.write_dispatch(
        wdhooks.workdir,
        {
            "event": "submitted",
            "dispatch_uuid": obj["dispatch_uuid"],
            **{key: obj[key] for key in NAMES},
            "dispatch": obj,
        },
    )
    return obj["dispatch_uuid"]
