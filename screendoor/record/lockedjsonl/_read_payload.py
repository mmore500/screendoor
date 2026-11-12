from ...auxlib._fold_trial_events import fold_trial_events
from ._files import path, read_events


def read_payload(*, timeout: float | None = None):
    """Read one dict per trial, under a shared lock; with ``raw``, the
    unfolded events."""

    def read_payload(ctx, *, raw: bool = False) -> list:
        events = read_events(path(ctx, "payload"), timeout)
        return events if raw else fold_trial_events(events)

    return read_payload
