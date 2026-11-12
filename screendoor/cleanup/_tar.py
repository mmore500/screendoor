import os
import tarfile

ARCHIVE = "trials.tar.gz"


def tar(ctx, *args, **kwargs) -> str | None:
    """Archive the run directory's ``trials/`` as ``trials.tar.gz`` beside it.

    Written to a temporary name and renamed into place, so a crash never
    leaves a partial archive under the final name. Returns the archive's
    path, or None if there is no ``trials/`` to archive. Extra arguments
    (what the cleanup hook was called with) are ignored.
    """
    trials = os.path.join(ctx.run_dir, "trials")
    if not os.path.isdir(trials):
        return None
    out = os.path.join(ctx.run_dir, ARCHIVE)
    tmp = f"{out}.tmp-{os.getpid()}"
    with tarfile.open(tmp, "w:gz") as archive:
        archive.add(trials, arcname="trials")
    os.replace(tmp, out)
    return out
