from ._validate import make_action


def progress(done: int, total: int, message: str | None = None) -> dict:
    """Report ``done`` of ``total`` steps complete.

    Parameters
    ----------
    done : int
        Steps complete.
    total : int
        Steps in all.
    message : str or None, default None
        A note to go with the counts.

    Returns
    -------
    dict
        The ``progress`` action.
    """
    kwargs = {"done": int(done), "total": int(total)}
    if message is not None:
        kwargs["message"] = str(message)
    return make_action("progress", **kwargs)
