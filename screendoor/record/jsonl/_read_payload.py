from ...auxlib._fold_trial_events import fold_trial_events
from ...auxlib._read_jsonl_tolerant import read_jsonl_tolerant
from ._files import path


def read_payload():
    """Read one dict per trial; with ``raw``, the unfolded events."""

    def read_payload(ctx, *, raw: bool = False) -> list:
        events = read_jsonl_tolerant(path(ctx, "payload"))
        return events if raw else fold_trial_events(events)

    return read_payload
