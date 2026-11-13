from ._validate import make_action


def warning(
    message: str, *, dedupe_key: str | None = None, data: dict | None = None
) -> dict:
    """Create a `warning` action, reporting a problem.

    Parameters
    ----------
    message : str
        The problem.
    dedupe_key : str or None, default None
        Key under which batching notifiers group repeats.
    data : dict or None, default None
        Extra JSON fields for the notifier.

    Returns
    -------
    dict
        The action.

    Raises
    ------
    ValueError
        If `data` is not JSON-serializable.
    """
    kwargs = {"message": str(message), "data": data or {}}
    if dedupe_key is not None:
        kwargs["dedupe_key"] = str(dedupe_key)
    return make_action("warning", **kwargs)
