import logging
import typing

from . import _run_slurm_command as _rsc


def poke() -> typing.Callable[[dict, list[dict]], set[str]]:
    """Create a `how_poke` hook that reports trials whose array task is no
    longer queued, with one `squeue` call per tick.

    `sacct` is asked how the gone jobs ended, for the log only.

    Returns
    -------
    Callable[[dict, list[dict]], set[str]]
        Hook `poke(ctx, trials)`, returning the `trial_uuid` of each trial
        whose array task is not queued; none if `squeue` fails.
    """

    def poke(ctx: dict, trials: list[dict]) -> set[str]:
        try:
            queued = _rsc.queued_jobs()
        except RuntimeError as e:
            logging.warning(
                "screendoor: squeue failed, assuming no change: %s", e
            )
            return set()

        def gone(t: dict) -> bool:
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
                    logging.info("screendoor: job left queue: %s", line)
        except RuntimeError as e:
            logging.warning("screendoor: sacct failed: %s", e)
        return {t["trial_uuid"] for t in trials}

    return poke
