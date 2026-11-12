from ._files import append, path


def write_trial_telemetry(*, timeout: float | None = None):
    """Append one event, with the dispatch's labels, to
    trial_telemetry.jsonl, under an exclusive lock."""

    def write_trial_telemetry(ctx, record: dict) -> dict:
        return append(
            path(ctx, "trial_telemetry"), {**ctx.labels, **record}, timeout
        )

    return write_trial_telemetry
