from ...auxlib._read_jsonl_tolerant import read_jsonl_tolerant
from ._files import path


def read_telemetry():
    """Read every event in telemetry.jsonl."""

    def read_telemetry(ctx) -> list:
        return read_jsonl_tolerant(path(ctx, "telemetry"))

    return read_telemetry
