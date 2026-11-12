from ._files import path, read_events


def read_telemetry(*, timeout: float | None = None):
    """Read every event in telemetry.jsonl, under a shared lock."""

    def read_telemetry(ctx) -> list:
        return read_events(path(ctx, "telemetry"), timeout)

    return read_telemetry
