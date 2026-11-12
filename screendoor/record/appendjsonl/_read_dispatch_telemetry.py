import os

from ...auxlib._read_jsonl_tolerant import read_jsonl_tolerant
from ._files import DISPATCH_TELEMETRY_FILE


def read_dispatch_telemetry():
    """Read every event in a workdir's dispatch_telemetry.jsonl."""

    def read_dispatch_telemetry(workdir: str) -> list:
        return read_jsonl_tolerant(
            os.path.join(workdir, DISPATCH_TELEMETRY_FILE)
        )

    return read_dispatch_telemetry
