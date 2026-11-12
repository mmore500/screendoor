import os

from ._files import DISPATCH_PAYLOADS_FILE, read_events


def read_dispatch_payloads(*, timeout: float | None = None):
    """Read every event in a workdir's dispatch_payloads.jsonl, under a
    shared lock."""

    def read_dispatch_payloads(workdir: str) -> list:
        file = os.path.join(workdir, DISPATCH_PAYLOADS_FILE)
        return read_events(file, timeout)

    return read_dispatch_payloads
