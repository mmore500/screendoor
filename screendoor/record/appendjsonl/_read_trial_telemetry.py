from ...auxlib._read_jsonl_tolerant import read_jsonl_tolerant
from ._files import path


def read_trial_telemetry():
    """Read every event in trial_telemetry.jsonl."""

    def read_trial_telemetry(ctx) -> list:
        return read_jsonl_tolerant(path(ctx, "trial_telemetry"))

    return read_trial_telemetry
