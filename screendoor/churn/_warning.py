from ._validate import make_action


def warning(message: str, dedupe_key: str | None = None) -> dict:
    """Warn; batched notifiers group repeats by ``dedupe_key``."""
    kwargs = {"message": str(message)}
    if dedupe_key is not None:
        kwargs["dedupe_key"] = str(dedupe_key)
    return make_action("warning", **kwargs)
