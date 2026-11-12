from __future__ import annotations

import logging
import typing

from . import _run_slurm_command as _rsc


def kill() -> typing.Callable[[dict, list[dict]], None]:
    """Cancel the trials' array tasks with one ``scancel``.

    Returns
    -------
    Callable[[dict, list], None]
        The ``how_kill`` hook: ``(ctx, trials)`` cancels those of the
        trials' array tasks still queued; a failure is logged, not raised.
    """

    def kill(ctx: dict, trials: list[dict]) -> None:
        try:
            queued = _rsc.queued_jobs()
            jobs = sorted(
                {
                    queued[key]
                    for t in trials
                    if t["job"]
                    and (key := (t["job"]["name"], t["job"]["index"]))
                    in queued
                }
            )
            if jobs:
                _rsc.run(["scancel", *jobs])
        except RuntimeError as e:  # e.g. a job that has already ended
            logging.warning("screendoor: %s", e)

    return kill
