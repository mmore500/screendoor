import logging

from . import _run_slurm_command as _rsc


def poke():
    """One squeue call per tick, plus sacct for jobs that left the queue."""

    def poke(ctx, launched: list) -> set:
        try:
            queued = _rsc.queued_job_ids()
        except RuntimeError as e:
            logging.warning(
                "screendoor: squeue failed, assuming no change: %s", e
            )
            return set()
        gone = {t["job_id"] for t in launched} - queued
        jobs = sorted(gone - {None})  # None: started, but launch unrecorded
        try:  # only to log how each job ended
            sacct = ["sacct", "--noheader", "--parsable2", "--allocations"]
            fmt = "--format=JobID,State,ExitCode"
            out = (
                _rsc.run([*sacct, "--jobs=" + ",".join(jobs), fmt])
                if jobs
                else ""
            )
            for line in out.splitlines():
                ctx.log("screendoor: job left queue: %s", line)
        except RuntimeError as e:
            logging.warning("screendoor: sacct failed: %s", e)
        return {t["trial_uuid"] for t in launched if t["job_id"] in gone}

    return poke
