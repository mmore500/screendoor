import logging
import os

from ..auxlib._DispatchContext import WorkdirHooks
from ..auxlib._append_jsonl_line import append_jsonl_line
from ..auxlib._now_iso import now
from ..auxlib._read_jsonl_tolerant import read_jsonl_tolerant


def notify_daemon(workdir: str, level: str, message: str) -> None:
    """Send one of the daemon's own notifications; never raises.

    ``level`` is ``liveness`` or ``termination``, each with a
    ``how_notify_<level>`` hook in ``screendoor.json``. The notifier gets
    the WorkdirHooks in place of a dispatch, and what it returns is
    appended to ``<workdir>/screendoor-notify.jsonl``.
    """
    try:
        hooks = WorkdirHooks(workdir)
        hook = getattr(hooks, f"notify_{level}")
        path = os.path.join(hooks.workdir, "screendoor-notify.jsonl")
        history = [
            e for e in read_jsonl_tolerant(path) if e.get("level") == level
        ]
        events = hook(hooks, level, message, {}, history, now()) or []
        if hasattr(hook, "flush"):
            events += hook.flush(hooks, level, history, now()) or []
        for event in events:
            fields = {"message": message, **event, "level": level}
            fields.pop("ts", None)
            append_jsonl_line(path, fields.pop("event", "sent"), **fields)
    except Exception:
        logging.exception("screendoor: daemon %s notification failed", level)
