def throttle():
    """Never throttle."""

    def throttle(ctx) -> bool:
        return True

    return throttle
