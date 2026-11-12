import logging

from . import _run_slurm_command as _rsc


def kill():
    """Cancel the trials' jobs with one ``scancel``."""

    def kill(ctx, trials: list) -> None:
        jobs = sorted({t["job_id"] for t in trials} - {None})
        try:
            if jobs:
                _rsc.run(["scancel", *jobs])
        except RuntimeError as e:  # e.g. a job that has already ended
            logging.warning("screendoor: %s", e)

    return kill
