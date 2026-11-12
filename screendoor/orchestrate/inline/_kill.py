def kill():
    """Inline trials end during launch, so there is never one to cancel."""

    def kill(ctx, trials: list) -> None:
        pass

    return kill
