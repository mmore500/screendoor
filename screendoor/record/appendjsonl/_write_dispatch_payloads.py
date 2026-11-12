import os

from ._files import DISPATCH_PAYLOADS_FILE, append


def write_dispatch_payloads():
    """Append one event to a workdir's dispatch_payloads.jsonl."""

    def write_dispatch_payloads(workdir: str, record: dict) -> dict:
        return append(os.path.join(workdir, DISPATCH_PAYLOADS_FILE), record)

    return write_dispatch_payloads
