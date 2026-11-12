def throttle():
    """Never throttle: inline trials end during launch."""

    def throttle(ctx) -> bool:
        return True

    return throttle
