import os
import tarfile
import typing

from ._clear import clear_trials

ARCHIVE = "trials.tar.gz"


def tar(*, clear: bool = False) -> typing.Callable[[dict, dict], None]:
    """Create a cleanup hook that archives the run directory's `trials/` as
    `trials.tar.gz` beside it.

    The archive is written under a temporary name and renamed into place,
    so that a crash never leaves a partial archive under the final name.

    Parameters
    ----------
    clear : bool, default False
        Whether to delete `trials/` once archived.

    Returns
    -------
    Callable[[dict, dict], None]
        Hook `tar(ctx, completed)`, usable as `how_cleanup_success` or
        `how_cleanup_failure`; it does nothing if there is no `trials/`.
    """

    def tar(ctx: dict, completed: dict) -> None:
        trials = os.path.join(ctx["run_dir"], "trials")
        if not os.path.isdir(trials):
            return
        out = os.path.join(ctx["run_dir"], ARCHIVE)
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
