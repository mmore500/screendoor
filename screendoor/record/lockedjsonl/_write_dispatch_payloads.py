import os

from ._files import DISPATCH_PAYLOADS_FILE, append


def write_dispatch_payloads(*, timeout: float | None = None):
    """Append one event to a workdir's dispatch_payloads.jsonl, under an
    exclusive lock."""

    def write_dispatch_payloads(workdir: str, record: dict) -> dict:
        file = os.path.join(workdir, DISPATCH_PAYLOADS_FILE)
        return append(file, record, timeout)

    return write_dispatch_payloads
