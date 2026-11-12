def poke():
    """Inline trials end during launch, so every launched trial is gone."""

    def poke(ctx, launched: list) -> set:
        return {t["trial_uuid"] for t in launched}

    return poke
