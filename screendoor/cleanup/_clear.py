import os
import shutil
import typing


def clear_trials(ctx: dict) -> None:
    """Delete the run directory's `trials/`, if there is one.

    Parameters
    ----------
    ctx : dict
        The hook context.
    """
    trials = os.path.join(ctx["run_dir"], "trials")
    if os.path.isdir(trials):
        shutil.rmtree(trials)


def clear() -> typing.Callable[[dict, dict], None]:
    """Create a cleanup hook that deletes the run directory's `trials/`.

    Returns
    -------
    Callable[[dict, dict], None]
        Hook `clear(ctx, completed)`, usable as `how_cleanup_success` or
        `how_cleanup_failure`.
    """

    def clear(ctx: dict, completed: dict) -> None:
        clear_trials(ctx)

    return clear
