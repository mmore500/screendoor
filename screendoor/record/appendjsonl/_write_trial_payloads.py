from ._files import append, path


def write_trial_payloads():
    """Append one event, with the dispatch's labels, to trial_payloads.jsonl."""

    def write_trial_payloads(ctx, record: dict) -> dict:
        return append(path(ctx, "trial_payloads"), {**ctx.labels, **record})

    return write_trial_payloads
