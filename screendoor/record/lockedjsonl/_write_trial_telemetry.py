from ._files import append, path


def write_trial_telemetry(*, timeout: float | None = None):
    """Append one event to
    trial_telemetry.jsonl, under an exclusive lock."""

    def write_trial_telemetry(ctx, record: dict) -> dict:
        return append(path(ctx, "trial_telemetry"), record, timeout)

    return write_trial_telemetry
