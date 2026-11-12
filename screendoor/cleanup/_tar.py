from __future__ import annotations

import os
import tarfile
import typing

from ._clear import clear_trials

ARCHIVE = "trials.tar.gz"


def tar(*, clear: bool = False) -> typing.Callable[[dict, dict], None]:
    """Archive the run directory's ``trials/`` as ``trials.tar.gz`` beside
    it; with ``clear``, then delete ``trials/``.

    The archive is written to a temporary name and renamed into place, so
    a crash never leaves a partial archive under the final name.

    Parameters
    ----------
    clear : bool, default False
        Whether to delete ``trials/`` once archived.

    Returns
    -------
    Callable[[dict, dict], None]
        A ``how_cleanup_success`` or ``how_cleanup_failure`` hook:
        ``(ctx, completed)`` archives ``trials/``, if there is one.
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
