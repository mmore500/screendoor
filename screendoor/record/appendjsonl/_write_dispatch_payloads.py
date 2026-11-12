import os

from ._files import DISPATCH_PAYLOADS_FILE, append


def write_dispatch_payloads():
    """Append one event to the dispatchdir's dispatch_payloads.jsonl."""

    def write_dispatch_payloads(ddhooks, record: dict) -> dict:
        return append(
            os.path.join(ddhooks.dispatchdir, DISPATCH_PAYLOADS_FILE), record
        )

    return write_dispatch_payloads
