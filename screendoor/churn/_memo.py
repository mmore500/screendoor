from ._validate import make_action


def memo(data: dict) -> dict:
    """Append assay-private state; churn runs again in the same tick.

    Parameters
    ----------
    data : dict
        The state, JSON-serializable; churn sees it in ``memo``.

    Returns
    -------
    dict
        The ``memo`` action.

    Raises
    ------
    TypeError
        If ``data`` is not a dict.
    ValueError
        If ``data`` is not JSON-serializable.
    """
    if not isinstance(data, dict):
        raise TypeError("memo data must be a dict")
    return make_action("memo", data=data)
