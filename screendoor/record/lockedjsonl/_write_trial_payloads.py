from ._files import append, path


def write_trial_payloads(*, timeout: float | None = None):
    """Append one event, with the dispatch's labels, to trial_payloads.jsonl,
    under an exclusive lock."""

    def write_trial_payloads(ctx, record: dict) -> dict:
        record = {**ctx.labels, **record}
        return append(path(ctx, "trial_payloads"), record, timeout)

    return write_trial_payloads
