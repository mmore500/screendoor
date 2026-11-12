import os
import shutil


def clear(ctx, *args, **kwargs) -> bool:
    """Delete the run directory's ``trials/``; return whether it existed.

    Extra arguments (what the cleanup hook was called with) are ignored.
    """
    trials = os.path.join(ctx.run_dir, "trials")
    if not os.path.isdir(trials):
        return False
    shutil.rmtree(trials)
    return True
