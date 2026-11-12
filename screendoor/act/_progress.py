from ._validate import make_action


def progress(done: int, total: int, message: str | None = None) -> dict:
    """Report ``done`` of ``total`` steps complete."""
    kwargs = {"done": int(done), "total": int(total)}
    if message is not None:
        kwargs["message"] = str(message)
    return make_action("progress", **kwargs)
