import logging
import os

from ..auxlib._DispatchContext import DispatchdirHooks
from ..auxlib._append_jsonl_line import append_jsonl_line
from ..auxlib._now_iso import now
from ..auxlib._read_jsonl_tolerant import read_jsonl_tolerant


def notify_daemon(dispatchdir: str, level: str, message: str) -> None:
    """Send one of the daemon's own notifications, through the
    `how_notify_<level>` hook of `dispatch_hooks.json`.

    The notifier's context is `{"dispatchdir": ...}`, with no
    `dispatch_uuid`, and the events it returns are appended to
    `<dispatchdir>/dispatch_notify.jsonl`. A notifier that raises is
    logged; this never raises.

    Parameters
    ----------
    dispatchdir : str
        Path of the daemon's dispatchdir.
    level : str
        `liveness` or `termination`.
    message : str
        The notification's text.
    """
    try:
        hooks = DispatchdirHooks(dispatchdir)
        hook = hooks.hook(f"how_notify_{level}")
        path = os.path.join(hooks.dispatchdir, "dispatch_notify.jsonl")
        history = [
            e for e in read_jsonl_tolerant(path) if e.get("level") == level
        ]
        ctx = hooks.hook_ctx
        events = hook(ctx, level, message, {}, history, now()) or []
        if hasattr(hook, "flush"):
            events += hook.flush(ctx, level, history, now()) or []
        for event in events:
            record = {"event": "sent", "message": message, **event}
            append_jsonl_line(path, {**record, "level": level})
    except Exception:
        logging.exception("screendoor: daemon %s notification failed", level)
