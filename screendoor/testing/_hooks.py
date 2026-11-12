"""Complete, explicit hook sets for tests and simulations.

screendoor gives no hook a default; these are what the test suite and
simulate_dispatch supply. A real dispatch spells out its own.
"""

import json
import os

from ..auxlib._DispatchContext import (
    DISPATCHDIR_HOOK_NAMES,
    FILES,
    HOOK_NAMES,
    LEVELS,
)

INLINE_HOOKS = {
    "how_launch": "scd.orch.inline.launch()",
    "how_poke": "scd.orch.inline.poke()",
    "how_kill": "scd.orch.inline.kill()",
    "how_throttle_churn": "scd.orch.inline.throttle()",
    "how_setup": "scd.record.appendjsonl.setup()",
    **{f"how_notify_{lv}": "scd.notify.log.notify()" for lv in LEVELS},
    **{
        f"how_{op}_{f}": f"scd.record.appendjsonl.{op}_{f}()"
        for f in FILES
        for op in ("read", "write")
    },
    "how_prep_trial_payloads": "scd.record.appendjsonl.prep_trial_payloads()",
    "how_unblock_churn": "scd.unblock.all_trials_ready()",
    "how_cleanup_success": "scd.cleanup.tar(clear=True)",
    "how_cleanup_failure": "lambda ctx, completed: None",
}
assert set(INLINE_HOOKS) == set(HOOK_NAMES)

DISPATCHDIR_HOOKS = {
    **{
        f"how_{op}_dispatch_{f}": f"scd.record.appendjsonl.{op}_dispatch_{f}()"
        for f in ("submissions", "payloads", "telemetry")
        for op in ("read", "write")
    },
    "how_log_info": "logging.info",
    "how_notify_liveness": "scd.notify.null.notify()",
    "how_notify_termination": "scd.notify.log.notify()",
}
assert set(DISPATCHDIR_HOOKS) == set(DISPATCHDIR_HOOK_NAMES)


def write_dispatchdir_hooks(dispatchdir: str, **overrides) -> str:
    """Write ``<dispatchdir>/screendoor.json`` with DISPATCHDIR_HOOKS and
    ``overrides``; return its path."""
    os.makedirs(dispatchdir, exist_ok=True)
    path = os.path.join(dispatchdir, "screendoor.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({**DISPATCHDIR_HOOKS, **overrides}, fh, indent=2)
    return path
