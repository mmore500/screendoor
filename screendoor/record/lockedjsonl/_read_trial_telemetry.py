from ._files import path, read_events


def read_trial_telemetry(*, timeout: float | None = None):
    """Read every event in trial_telemetry.jsonl, under a shared lock."""

    def read_trial_telemetry(ctx) -> list:
        return read_events(path(ctx, "trial_telemetry"), timeout)

    return read_trial_telemetry
