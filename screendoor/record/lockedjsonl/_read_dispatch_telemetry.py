import os

from ._files import DISPATCH_TELEMETRY_FILE, read_events


def read_dispatch_telemetry(*, timeout: float | None = None):
    """Read every event in the dispatchdir's dispatch_telemetry.jsonl, under a
    shared lock."""

    def read_dispatch_telemetry(ddhooks) -> list:
        file = os.path.join(ddhooks.dispatchdir, DISPATCH_TELEMETRY_FILE)
        return read_events(file, timeout)

    return read_dispatch_telemetry
