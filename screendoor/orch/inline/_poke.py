def poke():
    """Inline trials end during launch, so an unsettled one is gone."""

    def poke(ctx, trials: list) -> set:
        return {t["trial_uuid"] for t in trials}

    return poke
