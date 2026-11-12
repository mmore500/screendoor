import logging

from . import _run_slurm_command as _rsc


def poke():
    """One squeue call per tick: trials whose array task is not queued.

    sacct is asked how the gone jobs ended, for the log only.
    """

    def poke(ctx, trials: list) -> set:
        try:
            queued = _rsc.queued_jobs()
        except RuntimeError as e:
            logging.warning(
                "screendoor: squeue failed, assuming no change: %s", e
            )
            return set()

        def gone(t) -> bool:
            job = t["job"]
            return not job or (job["name"], job["index"]) not in queued

        trials = [t for t in trials if gone(t)]
        names = sorted({t["job"]["name"] for t in trials if t["job"]})
        try:
            if names:
                out = _rsc.run(
                    [
                        "sacct",
                        "--noheader",
                        "--parsable2",
                        "--allocations",
                        "--starttime=now-14days",
                        "--name=" + ",".join(names),
                        "--format=JobID,JobName,State,ExitCode",
                    ]
                )
                for line in out.splitlines():
                    ctx.log("screendoor: job left queue: %s", line)
        except RuntimeError as e:
            logging.warning("screendoor: sacct failed: %s", e)
        return {t["trial_uuid"] for t in trials}

    return poke
