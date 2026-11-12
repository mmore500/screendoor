from ._files import append, path


def write_trial_payloads():
    """Append one event to trial_payloads.jsonl."""

    def write_trial_payloads(ctx, record: dict) -> dict:
        return append(path(ctx, "trial_payloads"), record)

    return write_trial_payloads
