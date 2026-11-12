import logging

from . import _run_slurm_command as _rsc


def throttle(*, max_jobs: int):
    """Pass while fewer than ``max_jobs`` of your jobs are queued or
    running, counting each array task, of any job, as one."""

    def throttle(ctx) -> bool:
        try:
            return len(_rsc.queued_jobs()) < max_jobs
        except RuntimeError as e:
            logging.warning("screendoor: squeue failed, throttling: %s", e)
            return False

    return throttle
