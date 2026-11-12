from __future__ import annotations

import os
import shutil
import typing


def clear_trials(ctx: dict) -> None:
    """Delete the run directory's ``trials/``, if there is one.

    Parameters
    ----------
    ctx : dict
        The dispatch whose trials to delete.
    """
    trials = os.path.join(ctx["run_dir"], "trials")
    if os.path.isdir(trials):
        shutil.rmtree(trials)


def clear() -> typing.Callable[[dict, dict], None]:
    """Delete the run directory's ``trials/``.

    Returns
    -------
    Callable[[dict, dict], None]
        A ``how_cleanup_success`` or ``how_cleanup_failure`` hook:
        ``(ctx, completed)`` deletes ``trials/``, if there is one.
    """

    def clear(ctx: dict, completed: dict) -> None:
        clear_trials(ctx)

    return clear
