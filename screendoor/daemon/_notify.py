import logging

from ..auxlib._now_iso import now


def _history(ctx, level: str) -> list:
    events = ctx.hook("how_read_notify")(ctx)
    return [e for e in events if e.get("level") == level]


def _record(ctx, level: str, events: list, **defaults) -> None:
    for event in events or []:
        ctx.hook("how_write_notify")(
            ctx, {"event": "sent", **defaults, **event, "level": level}
        )


def notify(ctx, level: str, message: str, data: dict | None = None) -> None:
    """Hand a notification to its hook; never fails the tick."""
    try:
        hook = ctx.hook(f"how_notify_{level}")
        history = _history(ctx, level)
        events = hook(ctx, level, message, data or {}, history, now())
        _record(ctx, level, events, message=message)
    except Exception:
        logging.exception("screendoor: %s notification failed", level)


def flush_batched_notifications(ctx, levels) -> None:
    for level in levels:
        try:
            hook = ctx.hook(f"how_notify_{level}")
            if hasattr(hook, "flush"):
                events = hook.flush(ctx, level, _history(ctx, level), now())
                _record(ctx, level, events)
        except Exception:
            logging.exception("screendoor: flushing %s failed", level)
