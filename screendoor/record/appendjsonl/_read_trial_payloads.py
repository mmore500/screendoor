from ...auxlib._read_jsonl_tolerant import read_jsonl_tolerant
from ._files import path


def read_trial_payloads():
    """Read every event in trial_payloads.jsonl."""

    def read_trial_payloads(ctx) -> list:
        return read_jsonl_tolerant(path(ctx, "trial_payloads"))

    return read_trial_payloads
