import os

from ...auxlib._read_jsonl_tolerant import read_jsonl_tolerant
from ._files import DISPATCH_PAYLOADS_FILE


def read_dispatch_payloads():
    """Read every event in a workdir's dispatch_payloads.jsonl."""

    def read_dispatch_payloads(workdir: str) -> list:
        return read_jsonl_tolerant(
            os.path.join(workdir, DISPATCH_PAYLOADS_FILE)
        )

    return read_dispatch_payloads
