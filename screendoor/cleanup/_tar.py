import os
import tarfile

from ._clear import clear_trials

ARCHIVE = "trials.tar.gz"


def tar(*, clear: bool = False):
    """Archive the run directory's ``trials/`` as ``trials.tar.gz`` beside
    it; with ``clear``, then delete ``trials/``.

    The archive is written to a temporary name and renamed into place, so
    a crash never leaves a partial archive under the final name.
    """

    def tar(ctx, completed: dict) -> None:
        trials = os.path.join(ctx.run_dir, "trials")
        if not os.path.isdir(trials):
            return
        out = os.path.join(ctx.run_dir, ARCHIVE)
        tmp = f"{out}.tmp-{os.getpid()}"
        try:
            with tarfile.open(tmp, "w:gz") as archive:
                archive.add(trials, arcname="trials")
            os.replace(tmp, out)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        if clear:
            clear_trials(ctx)

    return tar
