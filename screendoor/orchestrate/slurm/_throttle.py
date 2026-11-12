import logging

from . import _run_slurm_command as _rsc


def throttle(*, max_jobs: int):
    """Pass while your job count in ``squeue --me`` is below ``max_jobs``."""

    def throttle(ctx) -> bool:
        try:
            return len(_rsc.queued_job_ids()) < max_jobs
        except RuntimeError as e:
            logging.warning("screendoor: squeue failed, throttling: %s", e)
            return False

    return throttle
