from ._procs import is_alive


def poke():
    """Report launched trials whose local process is no longer alive."""

    def poke(ctx, launched: list) -> set:
        jobs = {t["job_id"] for t in launched}
        alive = {j for j in jobs if j and j.startswith("pid:") and is_alive(j)}
        return {t["trial_uuid"] for t in launched if t["job_id"] not in alive}

    return poke
