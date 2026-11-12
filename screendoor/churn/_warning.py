from ._validate import make_action


def warning(
    message: str, *, dedupe_key: str | None = None, data: dict | None = None
) -> dict:
    """Warn of a problem; batched notifiers group repeats by
    ``dedupe_key``."""
    kwargs = {"message": str(message), "data": data or {}}
    if dedupe_key is not None:
        kwargs["dedupe_key"] = str(dedupe_key)
    return make_action("warning", **kwargs)
