import logging

from . import _run_slurm_command as _rsc


def kill():
    """Cancel the trials' array tasks with one ``scancel``."""

    def kill(ctx, trials: list) -> None:
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
