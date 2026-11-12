import os
import shutil


def clear_trials(ctx) -> None:
    """Delete the run directory's ``trials/``, if there is one."""
    trials = os.path.join(ctx.run_dir, "trials")
    if os.path.isdir(trials):
        shutil.rmtree(trials)


def clear():
    """Delete the run directory's ``trials/``."""

    def clear(ctx, completed: dict) -> None:
        clear_trials(ctx)

    return clear
