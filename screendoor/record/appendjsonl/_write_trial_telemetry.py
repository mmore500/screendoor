from ._files import append, path


def write_trial_telemetry():
    """Append one event to trial_telemetry.jsonl."""

    def write_trial_telemetry(ctx, record: dict) -> dict:
        return append(path(ctx, "trial_telemetry"), record)

    return write_trial_telemetry
