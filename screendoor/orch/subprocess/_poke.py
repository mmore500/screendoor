from ._procs import is_alive, pidfile


def poke():
    """Report trials whose batch's local process is not running."""

    def poke(ctx, trials: list) -> set:
        return {
            t["trial_uuid"]
            for t in trials
            if not (t["job"] and is_alive(pidfile(ctx, t["job"])))
        }

    return poke
