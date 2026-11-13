"""Notifier hooks (`how_notify_<level>`).

A notifier is called as `notify(ctx, level, message, data, history, now)`,
where `history` holds the level's earlier notification records, and
returns the records to append: `sent`, `queued`, `suppressed` or
`send_failed` events. A notifier with a `flush(ctx, level, history, now)`
attribute is also flushed at the end of each tick, to send what it has
held back.
"""

from ..auxlib._lazy_attach_stub import lazy_attach_stub

__getattr__, __dir__, __all__ = lazy_attach_stub(__name__, __file__)
