import os

from ._files import DISPATCH_TELEMETRY_FILE, append


def write_dispatch_telemetry():
    """Append one event to the dispatchdir's dispatch_telemetry.jsonl."""

    def write_dispatch_telemetry(ddhooks, record: dict) -> dict:
        return append(
            os.path.join(ddhooks.dispatchdir, DISPATCH_TELEMETRY_FILE), record
        )

    return write_dispatch_telemetry
