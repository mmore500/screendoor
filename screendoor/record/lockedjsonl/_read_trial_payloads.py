from ._files import path, read_events


def read_trial_payloads(*, timeout: float | None = None):
    """Read every event in trial_payloads.jsonl, under a shared lock."""

    def read_trial_payloads(ctx) -> list:
        return read_events(path(ctx, "trial_payloads"), timeout)

    return read_trial_payloads
