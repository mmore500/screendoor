import os

from ._files import DISPATCH_PAYLOADS_FILE, read_events


def read_dispatch_payloads(*, timeout: float | None = None):
    """Read every event in the dispatchdir's dispatch_payloads.jsonl, under a
    shared lock."""

    def read_dispatch_payloads(ddhooks) -> list:
        file = os.path.join(ddhooks.dispatchdir, DISPATCH_PAYLOADS_FILE)
        return read_events(file, timeout)

    return read_dispatch_payloads
