from __future__ import annotations

import logging
import typing

from ..auxlib._DispatchContext import LEVELS
from ..auxlib._now_iso import now

if typing.TYPE_CHECKING:
    from ..auxlib._DispatchContext import DispatchContext


def _history(ctx: DispatchContext, level: str) -> list[dict]:
    events = ctx.read_churn_notify()
    return [e for e in events if e.get("level") == level]


def _record(
    ctx: DispatchContext,
    level: str,
    events: list[dict] | None,
    **defaults: typing.Any,
) -> None:
    for event in events or []:
        ctx.write_churn_notify(
            {"event": "sent", **defaults, **event, "level": level}
        )


def notify(
    ctx: DispatchContext, level: str, message: str, data: dict | None = None
) -> None:
    """Hand a notification to its hook; never fails the tick.

    Parameters
    ----------
    ctx : DispatchContext
        The dispatch notifying.
    level : str
        One of LEVELS; the hook is ``how_notify_<level>``.
    message : str
        The notification text.
    data : dict or None, default None
        Extra fields for the notifier, such as ``dedupe_key``.
    """
    try:
        hook = ctx.hook(f"how_notify_{level}")
        history = _history(ctx, level)
        events = hook(ctx.hook_ctx, level, message, data or {}, history, now())
        _record(ctx, level, events, message=message)
    except Exception:
        logging.exception("screendoor: %s notification failed", level)


def flush_batched_notifications(ctx: DispatchContext) -> None:
    """Let each batching notifier send what it has held back.

    Parameters
    ----------
    ctx : DispatchContext
        The dispatch whose notifiers to flush.
    """
    for level in LEVELS:
        try:
            hook = ctx.hook(f"how_notify_{level}")
            if hasattr(hook, "flush"):
                history = _history(ctx, level)
                events = hook.flush(ctx.hook_ctx, level, history, now())
                _record(ctx, level, events)
        except Exception:
            logging.exception("screendoor: flushing %s failed", level)
