import os

from ._files import DISPATCH_TELEMETRY_FILE, read_events


def read_dispatch_telemetry(*, timeout: float | None = None):
    """Read every event in a workdir's dispatch_telemetry.jsonl, under a
    shared lock."""

    def read_dispatch_telemetry(workdir: str) -> list:
        file = os.path.join(workdir, DISPATCH_TELEMETRY_FILE)
        return read_events(file, timeout)

    return read_dispatch_telemetry
