from __future__ import annotations

import typing


def prep_trial_payloads() -> typing.Callable[[dict, int], None]:
    """Do nothing: a locked, appended trial_payloads.jsonl needs no room made.

    Returns
    -------
    Callable[[dict, int], None]
        The ``how_prep_trial_payloads`` hook: ``(ctx, n_trials)`` does
        nothing.
    """

    def prep_trial_payloads(ctx: dict, n_trials: int) -> None:
        pass

    return prep_trial_payloads
