import os

from ._files import DISPATCH_TELEMETRY_FILE, append


def write_dispatch_telemetry():
    """Append one event to a workdir's dispatch_telemetry.jsonl."""

    def write_dispatch_telemetry(workdir: str, record: dict) -> dict:
        return append(os.path.join(workdir, DISPATCH_TELEMETRY_FILE), record)

    return write_dispatch_telemetry
