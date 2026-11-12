import os

from ._files import DISPATCH_TELEMETRY_FILE, append


def write_dispatch_telemetry(*, timeout: float | None = None):
    """Append one event to the dispatchdir's dispatch_telemetry.jsonl, under an
    exclusive lock."""

    def write_dispatch_telemetry(ddhooks, record: dict) -> dict:
        file = os.path.join(ddhooks.dispatchdir, DISPATCH_TELEMETRY_FILE)
        return append(file, record, timeout)

    return write_dispatch_telemetry
