import contextlib
import os
import platform

from ...auxlib._DispatchContext import HOOK_DEFAULTS
from ...auxlib._get_screendoor_version import get_screendoor_version


def setup():
    """Create the run directory and record a ``setup`` event."""

    def setup(ctx) -> None:
        os.makedirs(os.path.join(ctx.run_dir, "trials"), exist_ok=True)
        with contextlib.suppress(OSError):
            os.chmod(ctx.workdir, 0o700)
        hooks = {}
        for name in sorted(HOOK_DEFAULTS):
            hooks[name] = {"expr": ctx.hook_expr(name)}
            try:
                hooks[name]["repr"] = repr(ctx.hook(name))
            except Exception as e:  # recorded here; raised when first used
                hooks[name]["error"] = repr(e)
        ctx.write_dispatch_payload(
            {
                "event": "setup",
                "run_dir": ctx.run_dir,
                "hooks": hooks,
                "screendoor_version": get_screendoor_version(),
                "python_version": platform.python_version(),
            },
        )
        ctx.is_setup = True

    return setup
