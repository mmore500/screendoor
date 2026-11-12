import os

from ._files import DISPATCH_PAYLOADS_FILE, append


def write_dispatch_payloads(*, timeout: float | None = None):
    """Append one event to the dispatchdir's dispatch_payloads.jsonl, under an
    exclusive lock."""

    def write_dispatch_payloads(ddhooks, record: dict) -> dict:
        file = os.path.join(ddhooks.dispatchdir, DISPATCH_PAYLOADS_FILE)
        return append(file, record, timeout)

    return write_dispatch_payloads
