from ._files import append, path


def write_trial_telemetry():
    """Append one event, with the dispatch's labels, to trial_telemetry.jsonl."""

    def write_trial_telemetry(ctx, record: dict) -> dict:
        return append(path(ctx, "trial_telemetry"), {**ctx.labels, **record})

    return write_trial_telemetry
